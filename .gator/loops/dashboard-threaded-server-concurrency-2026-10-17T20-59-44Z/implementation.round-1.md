# Implementation: Dashboard Threaded Request Server — Checkpoint 1 (Shared state snapshots)

## Revision Notes (findings round 1)

- **Finding 1 (Medium): responses written under `_STATE_WRITE_LOCK`. Fixed.**
  - `_handle_repo_register` now decides its outcome under the lock (the `ensure_dashboard_registry_entry` result, plus publication when `added`) and sends 409, 500 or 200 after release.
  - The same defect existed in `_handle_repo_remove`'s 404 path, and is fixed the same way: it records `removed`, publishes inside the lock when true, and responds after release.
  - Config POST already responded outside the lock; checked, unchanged.
  - New test `test_registry_responses_are_sent_outside_the_writer_lock`. It wraps `DashboardHandler._send_json` and records `_STATE_WRITE_LOCK.locked()` at every `/api/repos/*` response, across all five outcomes: register 409 (already registered), register 500 (simulated `ensure` failure), register 200, remove 404, remove 200. It asserts that none was sent under the lock and that the durable result is correct.
  - On the generation-0 code, this test fails and lists exactly the three rejection paths (register 409 and 500, remove 404).
  - Charter: the lock-order tripwire now says that no HTTP response is written under either state lock, rejections included, and names the pinning test.

## Executive Summary

- The registry and Fleet data are now read only through snapshot helpers, and replaced only through publish helpers under one writer lock. No route mutates a published value any more.
- Register, remove and config POST are copy-on-write. Register's and remove's registry-file read-modify-write runs under `_STATE_WRITE_LOCK`, so concurrent Dashboard registry writes to different paths never lose an update.
- The production server is still the single-request `HTTPServer`. Behavior for serialized use is unchanged.
- Verification: a new `tests/test_dashboard_concurrency.py` (6 tests on a test-local `ThreadingHTTPServer`). 3 of them fail on the base code, the response-under-lock test fails on generation 0, and all pass now. The listed verify suites, the Loop dashboard suites and two UI suites pass.

## Implementation Summary

`src/gator_command/scripts/gator-dashboard.py`:
- **New state helpers** (beside `_REGISTRY_REPOS`):
  - `_STATE_LOCK` is the leaf lock for reference reads and swaps. `_STATE_WRITE_LOCK` is the writer lock.
  - `_registry_snapshot()` returns `tuple(_REGISTRY_REPOS)`. `_registry_publish(records)` rebinds the global to a new tuple.
  - `_fleet_snapshot()` and `_fleet_publish(data)` read and rebind `DashboardHandler.fast_data`.
  - `_resolved_or_none()`; pure builders `_fleet_without(fleet, resolved_paths)` and `_fleet_with_repo_config(fleet, repo_name, config)`, which return a new dict and copy the changed entry.
- **Readers migrated** to one snapshot per use:
  - `_adopt_orphaned_loops`; `_resolve_repo_by_key` (one snapshot shared by both passes); `_handle_files` / `_handle_file` / `_handle_raw` / `_handle_history`; `_handle_audit_sessions`.
  - The `do_GET` branches for history, search, check, commits and Tier-2; the debug registry seam (one snapshot for the list and the count); `/api/data`; `_handle_repo_discover`; `_find_session_content`, including its Fleet fallback.
  - The `do_POST` config, topology, update and gatorize branches: `registry_repos=` and `fleet_data=` now receive snapshots, and `data.py` is unchanged.
  - `main()`: initial registry and Fleet go through publish under the writer lock. `global _REGISTRY_REPOS` is removed from `main()`.
- **Writers:**
  - `_handle_repo_register`: `ensure_dashboard_registry_entry` and the publication of `current + (record,)` both run under `_STATE_WRITE_LOCK`, with a resolved-path duplicate guard against the snapshot.
  - `_handle_repo_remove`: under `_STATE_WRITE_LOCK`, the steps keep their documented order: file write, then registry publish, then `_fleet_publish(_fleet_without(...))`, all before the response.
  - Config POST: writes `config.json`, then publishes `_fleet_with_repo_config(...)` under the writer lock.
  - The `/api/refresh` worker collects from a snapshot outside both locks, then publishes under the writer lock. Its admission (`locked()` check) is **unchanged on purpose**: single-flight and reconciliation belong to checkpoint 2.
- **Unchanged:** the test seams. Tests may still `monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", [...])` or assign `DashboardHandler.fast_data`, because the helpers read whatever is bound.

`tests/test_dashboard_remove.py::test_remove_repo_cache_coherence`: now asserts on `dashboard._registry_snapshot()`, and additionally that the seeded list is **not** mutated in place.

`tests/test_dashboard_concurrency.py` (new): a `threaded` fixture serves the real `DashboardHandler` from `ThreadingHTTPServer` over a temp registry file. It contains:
- `test_reads_keep_repo_identity_while_registry_changes` (pin 4): 80 reads over 8 workers (`/files` by name, `/sketch-sources` by key, `/api/data`) while a churner registers and removes four other repos. Each response contains its own repo's marker and never the other repo's, and `/api/data` is always a whole object.
- `test_duplicate_display_names_never_cross_repositories` (pin 4): name routes keep resolving the first registered match; key routes are exact.
- `test_remove_publishes_new_values_never_mutates_old`: snapshots held before a remove are unchanged afterwards.
- `test_concurrent_registers_for_different_paths_all_persist` (pin 4c): 12 barrier-synchronized registers; the file and the snapshot hold all 12.
- `test_concurrent_register_and_remove_for_different_paths` (pin 4c): 6 registers and 3 removes at once give the exact expected set in the file, the snapshot and the Fleet.

## Charter Updates

`.gator/charters/scripts-dashboard.md`:
- New entry `_registry_snapshot() / _registry_publish(records) / _fleet_snapshot() / _fleet_publish(data) / _fleet_without(...) / _fleet_with_repo_config(...) / _STATE_LOCK / _STATE_WRITE_LOCK`. It covers the purpose, readers and writers, a TRIPWIRE against mutating published values, the lock-order rule (writer lock, then state lock; no subprocess, Git, scan, Loop lock or `_refresh_lock` under them), the test-seam note, and the refresh note: publication now, admission in checkpoint 2.
- `_handle_repo_remove()`: the `->` line and the synchronous-publication tripwire now describe copy-on-write under the writer lock, plus register's and config's writer-lock behavior.
- `_resolve_repo_by_key`: `->` now names `_registry_snapshot()`.

Checked against the code: every name in the new heading exists in `gator-dashboard.py` (grep). `grep -n "_REGISTRY_REPOS\|fast_data"` now finds only the global declaration, the helpers themselves, and the class attribute.

## Verification

**Generation 1 runs:**
- `python -m pytest tests/test_dashboard_concurrency.py`: 6 passed.
- The new lock test alone, run against generation 0's staged `gator-dashboard.py`: 1 failed (`responses sent under _STATE_WRITE_LOCK: register 409, register 500, remove 404`).
- `python -m pytest tests/test_dashboard_remove.py tests/test_dashboard_loops.py tests/test_dashboard_sessions.py tests/test_dashboard_concurrency.py tests/test_dashboard_loop_brief.py tests/test_dashboard_loop_coding.py tests/test_dashboard_loop_liveness.py tests/test_dashboard_module_import.py tests/test_snapshot.py tests/test_dashboard_ui/test_harness.py`: **287 passed, 7 skipped**, with no failures. The intermittent `test_extend_attaches_one_watcher` failure noted below did not recur.

**Generation 0 runs (kept for the record):**

- `python -m pytest tests/test_dashboard_concurrency.py`: 5 passed. **Base check:** the same file run against `HEAD`'s `gator-dashboard.py` (with only the two read helpers appended) gives 3 failures: in-place mutation, and lost updates for both registry-writer races. So the tests detect the defect this checkpoint fixes.
- `python -m pytest tests/test_dashboard_remove.py tests/test_dashboard_loops.py tests/test_dashboard_sessions.py tests/test_dashboard_concurrency.py tests/test_dashboard_loop_brief.py tests/test_dashboard_loop_coding.py tests/test_dashboard_loop_liveness.py tests/test_dashboard_module_import.py tests/test_snapshot.py`: **265 passed, 6 skipped.** On the first run of this same set, one test failed once, `test_dashboard_loops.py::TestLoopExtend::test_extend_attaches_one_watcher`. It passed alone, passed in three consecutive full `test_dashboard_loops.py` runs (114 passed each), and passed in the full rerun above. I did not capture its assertion text. The test exercises `_LOOP_HOSTS` and watcher threads, which this checkpoint does not touch (only `_resolve_repo_by_key`'s registry read changed), so I report it as an intermittent failure of unconfirmed cause, not as fixed.
- `python -m pytest tests/test_dashboard_ui/test_harness.py tests/test_dashboard_ui/test_content_transport_slice1.py`: 91 passed, 1 skipped. These cover the real dashboard process, the debug registry seam, and content transport.
- Known gaps (by plan): refresh single-flight and reconciliation, `_repo_action`, the audit lock and Loop busy mapping (checkpoint 2); restart drain (checkpoint 3); the threaded production server and the remaining pins (checkpoint 4).
- Staged residue: `.gator/session-snippets/2026-10-17-gator-9368471a7e718.json` was already staged by the previous commit's hook (expected governance residue; it is swept into the next commit by design). `commit_draft.md` is updated in the working tree and is not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 4) — Shared state snapshots |
| Checkpoint base tree | `d42cac773e52d72e9734ad639ce30f744ce5b97a` |
| Generation | 1 |
| Staged tree (candidate) | `4841e1730af784d2c34b942a302e2d89578afdb1` |
| Changed paths in this checkpoint | 5 (A 2, M 3) |
| Loop base HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` |
| Loop base tree | `d42cac773e52d72e9734ad639ce30f744ce5b97a` |
| Current HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` (dev) |
| Changed paths vs loop base (cumulative) | 5 |
| Unstaged / untracked residue | 1 other + 16 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff d42cac773e52d72e9734ad639ce30f744ce5b97a 4841e1730af784d2c34b942a302e2d89578afdb1
```

Cumulative context (approved checkpoints plus this one): `git diff d42cac773e52d72e9734ad639ce30f744ce5b97a 4841e1730af784d2c34b942a302e2d89578afdb1`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard.md
A .gator/session-snippets/2026-10-17-gator-9368471a7e718.json
M src/gator_command/scripts/gator-dashboard.py
A tests/test_dashboard_concurrency.py
M tests/test_dashboard_remove.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 16 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
