# Implementation: Dashboard Threaded Request Server — Checkpoint 3 (Restart and upgrade drain)

## Executive Summary

- New `_LifecycleGate` counts in-flight POSTs. Once restart or upgrade starts draining, new POSTs get 503 `{"error": "dashboard is restarting"}`; GETs are not gated.
- `/api/restart` and `/api/updates/upgrade` are exempt from the gate, so the coordinator never waits for the request that triggered it. They start a `_drain_then(fn)` coordinator thread that waits up to `_DRAIN_SECONDS` (5 s) and then calls the unchanged `restart_server()` / `upgrade_and_restart()`.
- Only one coordinator ever starts. If its thread cannot start, draining is undone and the route returns 500, never a false `restarting`.
- Verification: 5 new tests (pin 6, `TestRestartDrain`); 33 in the module; 349 passed in the combined Dashboard and Loop suites.

## Implementation Summary

`src/gator_command/scripts/gator-dashboard.py`:
- **New constants:** `_DRAIN_SECONDS = 5.0`, `_GATE_EXEMPT_POSTS = {"/api/restart", "/api/updates/upgrade"}`, `_RESTARTING_ERROR`.
- **`_LifecycleGate`** (one `threading.Condition`):
  - `enter()` returns False once draining; `leave()` notifies at zero.
  - `start_draining()` returns True only for the first caller; `cancel_draining()` undoes it.
  - `wait_drained(timeout)` uses `Condition.wait_for`, so it holds no lock while waiting.
  - A read-only `draining` property.
- **Module singleton:** `_LIFECYCLE_GATE`.
- **`_drain_then(fn)`:** returns the coordinator body. It waits for the drain, prints a debug message if the bound expired with POSTs still in flight, then calls `fn()`.
- **`do_POST`:**
  - Runs `_check_post_auth()` (unchanged), then the gate.
  - Exempt paths go straight to `_post_routes(path)`. Other paths call `gate.enter()`; when refused, they drain the request body (the existing `_drain_request_body()`, for reliable delivery on Windows) and return 503. When admitted, they run `_post_routes(path)` with `try/finally: gate.leave()`.
  - `_post_routes()` holds the previous `do_POST` dispatch byte-for-byte, from the Loop routes on.
- **`DashboardHandler._start_lifecycle(fn, name)`:** called by the restart and upgrade routes **before** they respond.
  - If draining already started, it returns True and starts nothing.
  - Otherwise it starts a daemon thread named `dashboard-restart` / `dashboard-upgrade`. If `Thread.start()` raises, it cancels draining, sends 500 `could not start: …` and returns False.
  - The routes keep their responses `restarting` / `upgrading`.
- **`dashboard/updates.py` is unchanged.** `restart_server()` still sleeps 1 s for the response to flush, then calls `os.execv`. `upgrade_and_restart()` still spawns its helper, then calls `os._exit`.

## Charter Updates

`.gator/charters/scripts-dashboard.md`:
- `check_for_updates() / upgrade_and_restart() / restart_server()`: `<-` now says the routes call them through `_drain_then()`.
- New entry `_LifecycleGate / _LIFECYCLE_GATE / _drain_then(fn) / DashboardHandler._start_lifecycle(fn, name) / _post_routes(path) / _DRAIN_SECONDS / _GATE_EXEMPT_POSTS`. It covers:
  - the `do_POST` order: auth, gate, routes;
  - the exemption, and why it prevents a self-deadlock;
  - starting the coordinator before the response, and starting it only once;
  - the bounded wait without a held lock;
  - abandoned GETs and the Loop watcher, `host.lock` and adoption behavior;
  - the start-failure rule;
  - the gate condition as a leaf entered before any route lock;
  - the pinning test class.

Checked by grep: every heading name exists in the file.

## Verification

New `TestRestartDrain` in `tests/test_dashboard_concurrency.py`. An autouse fixture gives each test a fresh gate, because draining is one-way per process. `_restart_server` and `upgrade_and_restart` are monkeypatched to record calls.
- `test_restart_waits_for_an_in_flight_loop_post`:
  - A real `/pause` Loop POST is held *inside* the session lock (the real `_lock_exclusive`, then a gate).
  - `/api/restart` answers `restarting` within 2 s. A new register POST gets 503 `dashboard is restarting`, while `/api/data` still answers 200.
  - Restart has not run after 0.3 s. Once the Loop POST is released it completes with 200, and only then does restart run (its timestamp is after the release). The session reached `paused_by_architect`, so the transaction was not cut off.
- `test_restart_proceeds_after_the_drain_bound`: with `_DRAIN_SECONDS = 0.5` and a held register POST, restart runs about 0.5 s later regardless (bounded, no deadlock). The held POST then completes with 200.
- `test_repeat_restart_and_upgrade_start_one_coordinator`: two restarts and one upgrade during a drain all answer, and exactly one restart runs.
- `test_upgrade_drains_then_upgrades`: upgrade answers `upgrading` and calls `upgrade_and_restart` once.
- `test_coordinator_start_failure_undoes_draining`:
  - This test calls `_start_lifecycle` directly on a stub handler, with `threading.Thread` patched only for that call. Patching it during a live request would also break the server's own worker threads, so the first draft, which did that, failed with WinError 10053.
  - It gets False and a 500 `could not start`, and the gate is no longer draining: `enter()` admits again.

Runs:
- `python -m pytest tests/test_dashboard_concurrency.py`: 33 passed.
- **Base check:** against checkpoint 2's staged code, all 5 `TestRestartDrain` tests **error at setup**, because `_LifecycleGate` does not exist there. That shows the tests depend on the new code, not a behavioral failure of the old code. By reading: checkpoint 2's restart route started `_restart_server` on a thread immediately, with no drain and no 503, which is the behavior these tests forbid.
- Combined `tests/test_dashboard_remove.py tests/test_dashboard_loops.py tests/test_dashboard_sessions.py tests/test_dashboard_concurrency.py tests/test_dashboard_loop_brief.py tests/test_dashboard_loop_coding.py tests/test_dashboard_loop_liveness.py tests/test_dashboard_loop_attention.py tests/test_dashboard_module_import.py tests/test_snapshot.py tests/test_dashboard_ui/test_harness.py`: **349 passed, 7 skipped**, no failures.
- No other test references `/api/restart` or `/api/updates/upgrade` (grep over `tests/`).

Known gap (by plan): the real process replacement (`os.execv` / `os._exit`) is not exercised. The coordinator calls the unchanged functions, and the tests stop at the call.

Staged residue: the previous commit's session snippet, as before. `commit_draft.md` gained a checkpoint 3 line in the working tree; it is not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp3 (3 of 4) — Restart and upgrade drain |
| Checkpoint base tree | `42ed56931b0b7c4f9d7bb21521c4b66813985b6c` |
| Generation | 4 |
| Staged tree (candidate) | `87b50895006f835b8cba32c8ca35e8e9ed733fdd` |
| Changed paths in this checkpoint | 3 (M 3) |
| Loop base HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` |
| Loop base tree | `d42cac773e52d72e9734ad639ce30f744ce5b97a` |
| Current HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` (dev) |
| Changed paths vs loop base (cumulative) | 5 |
| Unstaged / untracked residue | 1 other + 22 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 42ed56931b0b7c4f9d7bb21521c4b66813985b6c 87b50895006f835b8cba32c8ca35e8e9ed733fdd
```

Cumulative context (approved checkpoints plus this one): `git diff d42cac773e52d72e9734ad639ce30f744ce5b97a 87b50895006f835b8cba32c8ca35e8e9ed733fdd`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/gator-dashboard.py  [revisits an earlier checkpoint]
M tests/test_dashboard_concurrency.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 22 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
