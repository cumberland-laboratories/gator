# Review: Dashboard Threaded Request Server — Checkpoint 1

## Executive Summary

- REVISE: the snapshot/publication conversion is otherwise well scoped and the staged tests exercise the intended registry and Fleet races.
- `_handle_repo_register()` writes its 409/500 response while `_STATE_WRITE_LOCK` is held.
- A response write is external I/O and can block on a slow client, extending a global registry writer critical section contrary to the lock-order contract and sketch principle.
- Release the writer lock before every response and add a focused regression check for the rejection paths.

## Verdict

REVISE

Checkpoint 1 must remove response I/O from the global state-writer critical section before it is safe to layer the threaded server on top.

## Findings

### Finding 1: Register rejection writes a response while holding `_STATE_WRITE_LOCK`

**Severity**: Medium

**Location**: `src/gator_command/scripts/gator-dashboard.py`, `_handle_repo_register()` inside `with _STATE_WRITE_LOCK`.

**Issue**: On `already_registered` and non-`added` results, `_handle_repo_register()` calls `self._send_json(...)` and returns from inside `_STATE_WRITE_LOCK`. The checkpoint's new charter contract says the state lock is a leaf for state operations and that writer locking covers only the read-modify-write; the approved plan's snapshot/work rule also explicitly excludes sending a response under a state lock. Under the threaded server, a blocked client write can therefore hold the global registry writer lock and unnecessarily stall unrelated register/remove publication.

**Suggestion**: Capture the result/status and leave `_STATE_WRITE_LOCK` before calling `_send_json` on every path (success is already outside the lock). Add a focused test or seam for both rejection outcomes that proves the lock is released before response emission, while retaining the serialized durable registry update/publication behavior.

## Scope Check

The candidate is within checkpoint 1 and its implementation artifact credibly records the affected Dashboard charter and tests. The checkpoint remains responsibility-based. This finding enforces the existing lock-boundary requirement; it does not add scope.

## What Looks Good

- Registry and Fleet publication now use whole-object replacement, and the removal test confirms old reader-held values are not changed in place.
- The writer-lock tests directly cover lost updates across different registry paths.
- The production server remains serialized, which keeps this checkpoint independently reviewable before request threading is enabled.

## Reviewed Candidate

<!-- Captured by the gator loop CLI at review submission. -->

| Fact | Value |
|---|---|
| Verdict | REVISE |
| Reviewed staged tree | `000dc4c746485938c34d8d9f21651fe50e3cd3dc` |
| Reviewed HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` |
| Candidate round | 0 |
| Checkpoint | cp1 (1 of 4) — Shared state snapshots |
| Checkpoint base tree | `d42cac773e52d72e9734ad639ce30f744ce5b97a` |
| Generation | 0 |
| Live candidate unchanged at review | yes |
