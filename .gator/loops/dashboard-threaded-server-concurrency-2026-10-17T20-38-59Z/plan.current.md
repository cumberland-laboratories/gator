# Implementation Plan: Dashboard Threaded Request Server

## Executive Summary

- Replace the single-request `HTTPServer` with a named `DashboardHTTPServer` (`ThreadingMixIn` + `HTTPServer`) that has a fixed worker cap (16) and a smaller "heavy work" class (4), so a slow `/files` or search cannot block an unrelated document, API or UI request.
- Key decision: make shared state safe **before** turning threading on. Registry and Fleet data become immutable snapshots, published under one short leaf lock; writers serialize under a separate writer lock; refresh becomes a true single-flight; every same-repository mutation (register, remove, update, gatorize, config, topology) takes one per-repository exclusion and re-checks registration under it.
- Main risks: lock-order mistakes and restart behavior. The plan fixes one documented lock order, keeps Loop locks authoritative, and drains in-flight POSTs (bounded) before restart.
- Verification: a new in-process threaded test module with gated handlers for the sketch's eight pins, a browser-level non-blocking proof, and the existing content-transport and Loop suites, on Windows and Linux.

## Revision Notes (round 1)

- **Finding 1 (High), remove outside the per-repository exclusion: accepted.**
  - Register and remove now take the same `_repo_action(<resolved path>)` as update, gatorize, config and topology. The busy result is the same 409.
  - Remove holds it from before the durable registry write through registry and Fleet publication and the response.
  - Update, gatorize, config and topology now resolve their action key in the route **before** any work. This includes update/gatorize's Fleet fallback, through a new `_resolve_action_target()`.
  - Each acquires `_repo_action`, then **re-checks under the lock** that the path is still registered (or still in the current Fleet, for the fallback). Only then does it start its subprocess or file write. If the repository was removed meanwhile, the action gets 404 and does nothing.
  - So a remove and a same-path action are strictly ordered: either the action finishes before the removal, or it is rejected (409 while it is running, 404 after). An action that started before the remove can never report success after the remove.
  - Register-versus-register and register-versus-remove are serialized twice: by `_repo_action` for the same path, and by `_STATE_WRITE_LOCK` around the registry-file read-modify-write and publication for different paths. The ordering is stated in the Lock order section.
  - Race tests for remove against register, update, gatorize, config and topology were added to pin 4. The work moved into checkpoint 2, which owns all mutation admission. Checkpoint 1 keeps only the copy-on-write publication.
- **Loop routes and remove (clarification).** Loop routes are key-addressed, and their authority is the Loop OS locks, so they do not take `_repo_action`. Remove is registry-only: it never touches `.gator/loops/`. A Loop request that resolved its key before a remove finishes against the repository files, exactly as the CLI would. Later key lookups get 404. This is the existing honest-stale-snapshot rule, now stated explicitly.

## Summary

The sketch asks for bounded, safe concurrent request handling in `gator-dashboard.py`. The audit below found that most route state is already request-local. The unsafe parts are four domains: the registry list, the Fleet object, refresh admission, and per-repository lifecycle writes. Two more need contracts: the audit-session cache and restart/upgrade. The Loop locks (`start.lock`, `host.lock`, `session.lock`, liveness lock) already exclude other threads in the same process, because every acquisition opens its own descriptor. So the Loop authority needs no new Dashboard lock, only honest error mapping. The plan delivers four checkpoints. Threading is switched on in the last one, so every earlier checkpoint is safe under the current serialized server.

## Context Checked

- No Architect brief: `gator loop status` lists none for this loop.
- `sketch.md` for this loop (scope, principles, eight verification pins, delivery sequence).
- `.gator/charters/INDEX.md` (routing), `.gator/charters/scripts-dashboard.md` (all sections, in particular `_handle_repo_remove`, `_resolve_repo_by_key`, `_LOOP_HOSTS` / `_ensure_loop_watcher`, loop control routes, `do_GET` / `do_POST`, `check_for_updates` / `restart_server`, `main`), `.gator/charters/scripts-cross-cutting.md` (loop revival and `start.lock` rule, the Dashboard registry pointer, package-data rules).
- `src/gator_command/scripts/gator-dashboard.py`: `_REGISTRY_REPOS`, `_LOOP_HOSTS_LOCK` / `_HostEntry` / `_run_watcher` / `_ensure_loop_watcher` / `_adopt_orphaned_loops`, `_resolve_repo_by_key`, `DashboardHandler` class attributes (`fast_data`, `_refresh_lock`, `_renotify_last` / `_renotify_lock`), `_handle_files`, `_handle_audit_sessions`, `do_GET` (all legacy branches, `/api/refresh`), `_handle_repo_discover`, `_handle_loop_start` (start-lock section), `_handle_repo_register`, `_handle_repo_remove`, `_find_session_content`, `do_POST` (config, topology, upgrade, restart, session, update, gatorize), `main()` (server construction and `serve_forever`).
- `src/gator_command/scripts/dashboard/data.py`: `load_registry_repos`, `resolve_repo_path`, `resolve_audit_sessions`, `resolve_repo_update`, `resolve_repo_gatorize`, `inject_repo_keys` (imported, not called by the server), `collect_standalone_data`.
- `src/gator_command/scripts/dashboard/updates.py`: `upgrade_and_restart`, `restart_server` (`os.execv` / `os._exit`).
- `src/gator_command/scripts/gator_core.py`: `read_dashboard_registry`, `write_dashboard_registry` (plain `write_text`), `ensure_dashboard_registry_entry`, `remove_dashboard_repo`, `import_sibling` (a fresh module per call, no shared cache).
- `src/gator_command/scripts/loop/host.py`: `_try_lock_exclusive_nb` (`msvcrt.locking` / `fcntl.flock` on a fresh `os.open` descriptor), `acquire_host_lock_with_retry`, `acquire_start_lock`. `src/gator_command/scripts/loop/session.py`: `_lock_exclusive` (blocking `LK_LOCK` on Windows, which raises `OSError` after about 10 s) and the session transaction that opens `session.lock` on every call. `src/gator_command/scripts/loop/liveness.py`: the lock-order header (leaf lock, reuses the session lock primitives).
- `src/gator_command/scripts/gator-session-aggregator.py` `_atomic_write` (unlink-then-rename on Windows; not safe for two concurrent writers).
- Tests: `tests/test_dashboard_remove.py` (asserts in-place mutation of the monkeypatched registry list), `tests/test_dashboard_loops.py` / `test_dashboard_loop_brief.py` / `test_dashboard_loop_coding.py` / `test_dashboard_loop_liveness.py` (build their own `HTTPServer` and monkeypatch `_REGISTRY_REPOS` and `DashboardHandler.fast_data`), `tests/test_dashboard_ui/_harness.py` (spawns the real dashboard process) and `test_harness.py` (debug registry seam).

## Shared-State Audit (result)

| Domain | Current shape (verified) | Threaded contract in this plan |
|---|---|---|
| Registry | module list `_REGISTRY_REPOS`; read by about 20 call sites; `append` in register; `[:] =` slice assignment in remove | immutable tuple, published by rebinding under `_STATE_LOCK`; read only through `_registry_snapshot()`; written only through `_registry_publish()` under `_STATE_WRITE_LOCK` |
| Fleet (`fast_data`) | class attribute; replaced by refresh; **mutated in place** by remove (`fast_data["repos"] = …`) and config POST (`r["config"].update`) | copy-on-write: writers build a new dict and publish it; nobody mutates a published object; readers take the reference under `_STATE_LOCK` |
| Refresh admission | `if not _refresh_lock.locked(): Thread(...)`: two requests can both start a worker; the second blocks and runs a second collection | `_refresh_lock.acquire(blocking=False)` in the request thread; the worker releases it in `finally`; if the thread fails to start, release it and return 500 |
| Refresh vs. remove | refresh publishes a result built from the pre-remove registry, which brings a removed repo back | at publication, reconcile against the current registry snapshot: drop Fleet repos whose resolved path is no longer registered |
| Lifecycle (register, remove, update, gatorize, config, topology) | register/remove rewrite the registry; update/gatorize run `gator-update` (60 s) / `gatorize` (120 s); config/topology write `.gator/`; all serialized today only by the server | one per-repository non-blocking exclusion `_repo_action(<resolved path>)` for all six. The action key is resolved before any work; registration is re-checked under the lock; a busy repository returns 409, a repository removed meanwhile returns 404; different repositories run in parallel |
| Audit sessions | `resolve_audit_sessions` writes the aggregator's cache through `_atomic_write`, which is not safe for two concurrent writers | route-local `_AUDIT_LOCK` serializes `/api/audit/sessions`; no other route takes it |
| Loop host registry | `_LOOP_HOSTS` + leaf `_LOOP_HOSTS_LOCK`; `host.lock` is the OS authority; adoption runs before `serve_forever` | unchanged. Verified: `_LOOP_HOSTS_LOCK` is never held while `host.lock` is acquired or a thread is joined. Two concurrent attaches: one gets `host.lock`, the other `already_hosted` |
| Loop control routes | delegate to `submit.*` / `host.*`; `start.lock` is non-blocking (409); `session.lock` is blocking | unchanged authority. New: an `OSError` from session-lock acquisition (Windows timeout under contention) maps to 503 "loop is busy; retry", not a dropped connection |
| Renotify rate limit | `_renotify_last` dict + `_renotify_lock` | already thread-safe; unchanged |
| Restart / upgrade | a daemon thread sleeps 1 s, then `os.execv` / `os._exit`; in-flight work is killed | `_LifecycleGate`: new POSTs get 503 while draining; wait up to 5 s for in-flight POSTs, then run the existing restart/upgrade unchanged |
| Debug seam | `/api/__gator_debug/registry_state` reads the live list | reads `_registry_snapshot()` |
| Request-local | handler instance, parse result, response writer; `import_sibling` (fresh module per call); `sys.path.insert` guards (a race can add a duplicate, which is harmless) | no change |

## Approach

### Lock order (one global order, documented in the charter)

```text
L1  route-exclusion locks (may be held across subprocess or file work):
      _repo_action(<resolved repo path>)   register / remove / update / gatorize / config / topology
      _AUDIT_LOCK                          /api/audit/sessions
      _refresh_lock                        single-flight token held by the refresh worker
L2  Loop OS locks (start.lock -> host.lock; session.lock; liveness lock)
      owned by loop/*; the Dashboard never holds L3/L4 while taking them
L3  _STATE_WRITE_LOCK   registry and Fleet writers only; small JSON file I/O
                        and Path.resolve() allowed; never a subprocess, Git,
                        repository scan, or Loop lock
L4  _STATE_LOCK         leaf; reference read/swap only, no I/O
leaf  _LOOP_HOSTS_LOCK, _renotify_lock, _REPO_ACTION_GUARD, _LifecycleGate condition
```

Registry-writer ordering: register and remove take `_repo_action(path)` (L1) first, then `_STATE_WRITE_LOCK` (L3) for the registry-file read-modify-write and publication, then L4 for the swap. Two writers for the same path conflict at L1 (the second gets 409). Writers for different paths are serialized at L3, so the read-modify-write never loses an update.

Rules: locks are acquired only in the direction L1 -> L3 -> L4. No thread holds L3 or L4 while it acquires L1, an L2 lock, or waits on a subprocess. Readers take only L4, and only for a reference read. A request never waits for refresh: refresh admission is non-blocking.

### Server shape

`DashboardHTTPServer(socketserver.ThreadingMixIn, HTTPServer)` in `gator-dashboard.py`:
- `daemon_threads = True`: Ctrl+C and `os.execv` never wait for a stuck worker.
- `block_on_close = False`.
- `request_queue_size = 64`: connections above the worker cap wait in the listen backlog instead of being refused.
- `MAX_WORKERS = 16`: a `BoundedSemaphore` acquired (blocking) in `process_request` before the worker starts, and released in `process_request_thread`'s `finally`. If the thread fails to start, the slot is released and `shutdown_request` closes the connection.
- `HEAVY_WORKERS = 4`: `_heavy_work()`, a context manager over a second `BoundedSemaphore`, wraps `/files` (live and versioned), `/search`, Tier-2 `/api/repo/<name>`, `/check`, `/history`, `/commits`, `/api/repos/discover` and `/api/audit/sessions`. It acquires with a 60 s timeout; on timeout the route returns 503 "dashboard busy". At least 12 workers therefore always stay free for small reads.
- Loopback bind is unchanged. `protocol_version` stays HTTP/1.0, so each connection carries one request and one worker. Charter tripwire: HTTP/1.1 keep-alive would pin workers to idle connections.

Why bounded rather than plain `ThreadingHTTPServer`: a browser opens at most 6 HTTP/1.x connections per origin, so normal use stays well under 16. A cap still stops runaway clients and tests from creating unbounded threads (sketch principle 5), and the heavy class keeps parallel listings from saturating disk or CPU. Both constants are module-level and get re-measured in checkpoint 4 (assumption, see below).

### State helpers (`gator-dashboard.py`)

- `_registry_snapshot() -> tuple`: under L4, `tuple(_REGISTRY_REPOS)`. Reading the module global keeps existing `monkeypatch.setattr(dashboard, "_REGISTRY_REPOS", [...])` tests working. Records are never mutated after publication.
- `_registry_publish(records)`: under L4, rebinds `_REGISTRY_REPOS = tuple(records)`. Callers must hold L3.
- `_fleet_snapshot()`: under L4, returns the `DashboardHandler.fast_data` reference. The class attribute stays the publication slot, so existing tests that assign it still work.
- `_fleet_publish(data)`: under L4, rebinds `DashboardHandler.fast_data`. Callers must hold L3.
- `_fleet_without(paths)` / `_fleet_with_repo_config(name, config)`: pure builders that return a new dict (new `repos` list, copied entry for the changed repo).
- `_repo_action(repo_path)`: a context manager over a per-resolved-path `threading.Lock` (dict guarded by `_REPO_ACTION_GUARD`; entries kept, bounded by registry size plus attempted paths). Non-blocking acquire; it yields False when busy. The key is always `str(Path(p).resolve())`, computed before the lock.
- `_resolve_action_target(repo_name, registry, fleet) -> (path | None, source)`: the same lookup `data.resolve_repo_update` / `resolve_repo_gatorize` do today (registry by name, else the accessible Fleet entry by name), lifted into the route so the key is known before work. `_still_targeted(path, source)` re-checks it under `_repo_action` against fresh snapshots: the path is still registered, or for the Fleet fallback, still in the current Fleet.

All call sites that read `_REGISTRY_REPOS` or `self.__class__.fast_data` switch to the snapshot helpers. They take one snapshot at route entry, and from then on resolve paths and do their work from that copy. A remove that makes a snapshot stale gives an honest filesystem error, never a fallback to another repository.

## Changes

### 1. State snapshot and publication helpers
- File: `src/gator_command/scripts/gator-dashboard.py`
- What: add `_STATE_LOCK`, `_STATE_WRITE_LOCK` and the four snapshot/publish helpers plus the two pure Fleet builders. Migrate every reader: `_adopt_orphaned_loops`, `_resolve_repo_by_key`, `_handle_files` / `_handle_file` / `_handle_raw` / `_handle_history`, `_handle_audit_sessions`, all `do_GET` legacy branches, the debug seam, `_handle_repo_discover`, `_find_session_content`, and the `do_POST` config / topology / update / gatorize branches (they pass `registry_repos=` and `fleet_data=` snapshots to `data.py`).
- Why: one authority per state domain (sketch principle 3); readers never see partial data.

### 2. Registry and Fleet writers
- File: `src/gator_command/scripts/gator-dashboard.py`
- What: `_handle_repo_register` and `_handle_repo_remove` run their `gator_core` call and the in-memory update under L3, then publish a new registry tuple and, for remove, a new Fleet object. Register checks the snapshot for an existing resolved path before it appends. Config POST writes `config.json` outside L3 (inside `_repo_action`), then publishes `_fleet_with_repo_config` under L3. Remove keeps its documented order: registry file, then registry snapshot, then Fleet, all before the success response.
- Why: no lost update between two Dashboard registry writes; no in-place mutation of the published Fleet object. Same-path ordering against other lifecycle actions is added in Change 4.

### 3. Refresh single-flight and reconciliation
- File: `src/gator_command/scripts/gator-dashboard.py`
- What: `/api/refresh` calls `_refresh_lock.acquire(blocking=False)`. When it succeeds, the worker does `collect_standalone_data(_registry_snapshot())` outside L3/L4, then under L3 reconciles the result against the current registry snapshot and publishes it. The worker releases `_refresh_lock` in `finally`. The response values `refreshing` and `already_refreshing` are unchanged.
- Why: exactly one collection; a stale but coherent Fleet; a removed repository never comes back.

### 4. Route exclusions and Loop busy mapping
- File: `src/gator_command/scripts/gator-dashboard.py`
- What: `_repo_action` wraps all six same-repository mutations (busy: 409 `{"error": "another change is running for this repository"}`):
  - **remove:** resolve the path, then `_repo_action`, then under L3 `remove_dashboard_repo`, publish the registry, publish the Fleet; release after the response is written.
  - **register:** resolve, `_repo_action`, then under L3 `ensure_dashboard_registry_entry` and publish.
  - **update / gatorize:** `_resolve_action_target`, `_repo_action`, `_still_targeted` (404 `{"error": "repo '<name>' not found"}` if it was removed), then call `resolve_repo_update` / `resolve_repo_gatorize` with a one-entry registry snapshot holding exactly that path. The existing `data.py` validation (`.gator/` present or absent, accessibility) and subprocess run unchanged inside the lock. Pass the snapshot only; `data.py` needs no code change.
  - **config / topology:** the same resolve, lock and re-check, then the file write; config then publishes the Fleet copy under L3.
  
  The response is always written while `_repo_action` is still held, so no success for a same-path action can be reported after a remove that followed it. `_AUDIT_LOCK` wraps `_handle_audit_sessions`. In the Architect control handlers (`_handle_loop_pause` / `interject` / `unblock` / `end` / `extend` / `reopen`), an `OSError` raised while acquiring the session lock maps to 503 `{"error": "loop is busy; retry"}`. `PermissionError` (409), `ValueError` (400) and `RuntimeError` (409) keep their current mapping. The Dashboard still never takes `session.lock` itself.
- Why: same-repository mutation stays serialized while unrelated repositories run in parallel; the second of two racing Loop requests gets an honest error.

### 5. Restart and upgrade drain
- File: `src/gator_command/scripts/gator-dashboard.py` (`dashboard/updates.py` unchanged)
- What: `_LifecycleGate`, a condition with an `in_flight` count and a `draining` flag. `do_POST` enters the gate after `_check_post_auth`, except for `/api/restart` and `/api/updates/upgrade`, which are never counted, so the coordinator never waits for the request that triggered it. A gated POST that arrives while draining gets 503 `{"error": "dashboard is restarting"}`. The restart and upgrade routes respond as today, then start `_drain_then(fn)` on a new daemon thread: set `draining`, wait up to 5 s for `in_flight == 0` (holding only the condition, which `wait` releases), then call the unchanged `restart_server` / `upgrade_and_restart`. In-flight GETs are abandoned; they are read-only, and the browser already reconnects after a restart. Running Loop watcher threads die with the process as today; `host.lock` is released by the OS, and adoption re-hosts after the restart.
- Why: no deadlock on the triggering request; no Loop transaction cut mid-write by `os._exit` when it can finish within 5 s; no false success.

### 6. Threaded server with admission
- File: `src/gator_command/scripts/gator-dashboard.py`
- What: add `DashboardHTTPServer`, `MAX_WORKERS`, `HEAVY_WORKERS` and `_heavy_work()`; wrap the heavy routes; `main()` constructs `DashboardHTTPServer` on both bind paths. The `Ready on` line and loopback bind are unchanged.
- Debug seam (test-only): when `GATOR_DASHBOARD_DEBUG=1` **and** `GATOR_DASHBOARD_DEBUG_FILES_GATE=<path>` are set, `_handle_files` waits (up to 30 s) until that file exists before listing. It follows the existing debug-seam rule: without `GATOR_DASHBOARD_DEBUG=1`, nothing changes.
- Why: the sketch's user promise. The gate gives the browser-level proof a deterministic slow listing.

### 7. Tests
- New `tests/test_dashboard_concurrency.py`: an in-process fixture that serves `DashboardHandler` from `DashboardHTTPServer` on port 0, with seeded registry and repositories and bounded `threading.Event` gates installed with monkeypatch. Every wait has a timeout, and on failure the test reports `threading.enumerate()` names and request outcomes.
- `tests/test_dashboard_remove.py::test_remove_repo_cache_coherence`: assert on `dashboard._REGISTRY_REPOS` (the published snapshot) instead of the identity of the monkeypatched list. This is the only existing assertion that depends on in-place mutation.
- Existing Loop/remove fixtures that construct `HTTPServer` stay as they are (serialized behavior is still valid). The concurrency module covers the threaded class.
- New Playwright test `tests/test_dashboard_ui/test_request_concurrency_ui.py`, which uses the files-gate seam (see checkpoint 4).

## Dependencies and Ordering

Changes 1 -> 2 -> 3 -> 4 -> 5 -> 6. Changes 1–5 are correct under the current serialized server, so each checkpoint ships safely. Change 6 turns on concurrency only after every shared domain has its contract. Tests land with the checkpoint they verify.

## Assumptions, Risks, and Required Architect Decisions

- **Assumption (non-blocking): worker caps 16 / 4 and the 60 s heavy timeout.** Chosen from the browser's 6-connections-per-origin limit and the sketch's "conservative" direction. Checkpoint 4 measures concurrent listings on this repository and may lower `HEAVY_WORKERS`; the Architect may set other values.
- **Assumption (non-blocking): 409 for a busy repository action.** This rejects instead of queuing, because update/gatorize can take minutes and a queued second run would repeat the first. The UI already shows server error text.
- **Assumption (non-blocking): a 5 s drain bound** before restart/upgrade. Longer Loop POSTs are rare (session transactions are milliseconds; `extend` / `reopen` may wait about 3 s for `host.lock`).
- **Risk: cross-process registry writes.** `gator init` / `gatorize` in another process still do an unlocked read-modify-write with a non-atomic `write_text` (`gator_core`, which this charter does not own). This is pre-existing and out of scope; the plan serializes only Dashboard-internal writers. It is recorded as a charter note.
- **Risk: duplicate display names.** Name-addressed routes still resolve the first registered match (pre-existing; inbox note of 2026-10-17). Concurrency tests pin that a route never resolves a *different* repository than it did before, and that key-addressed routes are exact.
- **Risk: the session lock on Windows** blocks a worker for up to about 10 s under contention. The 16-worker cap and the 503 mapping bound the effect.
- **Non-goal kept:** no change to `/files` cost, to content policy, CSP, tokens, or containment, or to the browser scheduling and polling work. Threading is not claimed to close #70.

## Testing

`tests/test_dashboard_concurrency.py` covers the sketch pins:
1. **Head-of-line:** gate a real `/files` handler (monkeypatched `_iter_scanner_files` waits on an Event). While it is held, `/file/<doc>` and `/raw/<html>` for the same repository return 200 within 2 s. Then release the gate; the listing completes.
2. **Concurrent reads, two repositories:** 8 threads × 25 mixed `/files`, `/raw`, `/api/data` and Loop `/status` requests across repos A and B. Every response has the right repository identity (listing entries and file bytes belong to the requested repo) and the expected security headers (`nosniff`, `Cache-Control`, the HTML CSP pair and `Vary: Sec-Fetch-Dest` on `/raw`).
3. **Refresh single-flight:** monkeypatch `collect_standalone_data` to count calls and wait on a gate. Ten concurrent `/api/refresh` calls give exactly one `refreshing` and nine `already_refreshing`, and the collector runs once. Concurrent `/api/data` readers each see either the complete old object or the complete new one (marker field), never a mix.
4. **Register/remove under reads:** reads loop while repositories are registered and removed, including two repositories that share a display name and differ in key. No 500; key routes resolve only their own repository; a refresh that started before a remove does not bring the removed repository back (reconciliation).
   **Remove versus same-path mutations** (`run_text` and the `gator_core` writers monkeypatched with Event gates, so each action can be held mid-flight):
   - (a) An update or gatorize is held inside its subprocess, and a remove for the same path arrives. The remove gets 409 and the registry is unchanged. After the update finishes, a retried remove succeeds.
   - (b) A remove is held inside its registry write, and an update, gatorize, config or topology for the same path arrives. It gets 409. A retry after the remove completes gets 404: no subprocess call is recorded and `config.json` is not written.
   - (c) Register versus remove, and two registers, for the same path: exactly one wins and the other gets 409. Registers for two different paths running at once both persist; the registry file holds both, so no update is lost.
   - In every case, no success response for a same-path mutation is timestamped after the remove's success response.
5. **Loop races:** two concurrent `/extend` (and two `/reopen`, two `/loops/start`) against one loop give exactly one success. The other gets 409 (`start.lock` / stage) or 503 (busy). `session.json` and `events.jsonl` show exactly one transition, and at most one watcher is attached.
6. **Restart under load:** with `restart_server` / `upgrade_and_restart` monkeypatched to record calls, a gated in-flight Loop POST delays the restart until it finishes. A gated POST longer than the drain bound does not stop the restart from starting after about 5 s. A new POST during the drain gets 503. The restart request itself returns `restarting` at once. No deadlock: every join has a timeout.
7. **Content transport under the threaded server:** the Playwright content-transport suites (`test_content_transport_slice1/2/3`, `test_html_preview`) already run against the real dashboard process. After checkpoint 4 that process uses `DashboardHTTPServer`, so they re-verify traversal, symlink/junction, override internals, versioned reads, CSP and the no-oracle 404s. The concurrency module also re-runs a parametrized subset of those negative requests concurrently (16 at once) and asserts identical status codes and bodies to the serial run.
8. **Stress:** a bounded mixed workload (reads, register/remove, refresh, config POST, Loop status) of 400 requests over 12 threads with a 90 s overall timeout. It runs in the normal suite on Windows and Linux CI with no automatic rerun, and dumps thread names and outstanding requests on failure.

Browser level (`test_request_concurrency_ui.py`): set the files-gate seam, open a repository and select an HTML document. The document frame finishes loading while the listing is still gated. Then release the gate.

Regression: the full `tests/test_dashboard_*.py`, `tests/test_dashboard_ui/` and `tests/test_loop*.py` suites. Performance check (recorded in the implementation artifact): with the files gate held, time a small `/file` request; also time 1 versus 4 concurrent real `/files` listings on this repository to confirm `HEAVY_WORKERS` and that per-listing cost is not hidden.

## Charter Impact

- `.gator/charters/scripts-dashboard.md`: new entries for `DashboardHTTPServer` / `MAX_WORKERS` / `HEAVY_WORKERS` / `_heavy_work()`, `_registry_snapshot()` / `_registry_publish()` / `_fleet_snapshot()` / `_fleet_publish()`, `_repo_action()` / `_resolve_action_target()` / `_still_targeted()` (all six same-repository mutations; resolve the key first, re-check under the lock, write the response while holding it), `_AUDIT_LOCK`, and `_LifecycleGate` / `_drain_then()`. A **lock-order tripwire** holds the L1–L4 order above. Updated entries: `_handle_repo_remove` (copy-on-write publication replaces in-place cache mutation), `do_GET` refresh (single-flight and reconciliation), `main()` (server class), loop control routes (503 busy mapping), debug seams (files gate), HTTP/1.0 tripwire, and a note on cross-process registry writes.
- `.gator/charters/scripts-cross-cutting.md`: one line in the Loop lock paragraph: Dashboard state locks are never held while a Loop OS lock is acquired, and `_LOOP_HOSTS_LOCK` stays a leaf.
- `.gator/charters/scripts-dashboard-ui.md`: no change; there is no browser code change. Only the new test is referenced if the charter lists UI tests.
- `scripts-loop.md`, `scripts-core-library.md`: no change (no Loop or `gator_core` code changes).

## Coding Checkpoints

1. **Shared state snapshots** — add `_STATE_LOCK` / `_STATE_WRITE_LOCK`, the registry and Fleet snapshot/publish helpers, and the pure Fleet builders; migrate every reader to snapshots; make register, remove and config publish copy-on-write under the writer lock (so different-path registry writers never lose an update); update the remove cache-coherence test. The server stays serialized.
  Verify: `tests/test_dashboard_remove.py`, `tests/test_dashboard_loops.py`, `tests/test_dashboard_sessions.py`, plus the pin 4 read-coherence tests and the different-path register race (pin 4c), run against a test-local `ThreadingHTTPServer`.
2. **Mutation admission** — refresh single-flight with reconciliation; `_repo_action` with `_resolve_action_target` / `_still_targeted` for all six same-repository mutations (register, remove, update, gatorize, config, topology); `_AUDIT_LOCK`; the Loop busy (503) mapping.
  Verify: new concurrency tests for pin 3, pin 5, and the remove-versus-same-path tests 4a–4c; the Loop dashboard suites.
3. **Restart and upgrade drain** — `_LifecycleGate`, the 503 for POSTs while draining, and `_drain_then()` around the unchanged restart/upgrade functions.
  Verify: new concurrency tests for pin 6 (with restart/upgrade monkeypatched).
4. **Threaded server** — `DashboardHTTPServer` with worker and heavy-work admission, the heavy-route wrapping, `main()` construction, and the debug files-gate seam; the browser-level proof and the stress test.
  Verify: concurrency pins 1, 2, 7 and 8; `tests/test_dashboard_ui/test_request_concurrency_ui.py`; the full `tests/test_dashboard_ui/` suite; the recorded performance check.
