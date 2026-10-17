# Implementation: Dashboard Threaded Request Server — Checkpoint 2 (Mutation admission)

## Revision Notes (findings round 1)

- **Finding 1 (High): busy mapping not tied to a verified Windows signal. Accepted and resolved by measuring the real boundary.**
  - **Measured on this machine** (Windows 10, Python 3.13): two handles on one file. The second `msvcrt.locking(fd, LK_LOCK, 1)` raised `OSError(36, 'Resource deadlock avoided')` after 9.1 s. errno 36 is `errno.EDEADLOCK`, which equals `errno.EDEADLK` on Windows; there is no `winerror`. So the generation-2 classifier was correct, but nothing proved it, and the tests only injected the errno.
  - **New `test_real_windows_session_lock_contention_maps_to_503`** (Windows-only, `skipif` elsewhere with the reason). It holds the loop's real `session.lock` with `msvcrt.locking` from another handle, then POSTs `/pause` through the real path: `submit.handle_pause` → `session.with_session_lock` → `_lock_exclusive`. It asserts 503 `{"error": "loop is busy; retry"}`, that the request waited for the timeout (at least 5 s), and that `session.json` is byte-identical. It passes. If a future Python or OS changes the signal, this test fails instead of letting the mapping silently miss.
  - **New `test_other_session_lock_errors_are_not_reported_busy`.** A non-contention `OSError(EIO)` from the lock boundary keeps its previous behavior: it is unhandled and the connection drops. It never becomes 503, and nothing is written.
    - While writing it, I found that `OSError(EACCES, …)` is constructed as `PermissionError`, which these routes already map to 409 (unchanged).
    - The errno-classifier unit test now uses `EIO` for its negative case.
  - **Why the classifier stays in the Dashboard** rather than a new Loop-side exception: the approved plan keeps `loop/*` unchanged. The boundary is now proven at the exact call it classifies, `msvcrt.locking` inside `session._lock_exclusive`, by a real-lock test rather than an assumption.
  - **POSIX:** `fcntl.flock(LOCK_EX)` blocks without a timeout, so it never produces this error. That is stated in the code comment and the charter.
  - **Code comment and charter** now name the measured boundary, the pinning tests, and the rule for a changed platform signal: re-measure and update `_LOOP_LOCK_BUSY_ERRNOS`; never widen to every `OSError`.

## Executive Summary

- All six same-repository mutations (register, remove, update, gatorize, config, topology) now run under one per-resolved-path `_repo_action` exclusion. Each resolves its target first and re-checks it under the lock: 409 if the repository is busy, 404 if it was removed meanwhile, and its response is written while the lock is still held.
- Refresh is single-flight (one non-blocking acquire; the worker releases it in `finally`), and it reconciles with removals at publication.
- `/api/audit/sessions` is serialized by `_AUDIT_LOCK`. A session-lock timeout (`EDEADLK`) in the six Architect Loop actions maps to 503 "loop is busy; retry". Other `OSError`s propagate unchanged.
- Verification: 23 new tests (28 in the module), including a real Windows `session.lock` contention test. Run against checkpoint 1's code, 16 fail. Combined Dashboard and Loop suites: 342 passed, 7 skipped; one earlier run had a single intermittent failure, reported below.

## Implementation Summary

`src/gator_command/scripts/gator-dashboard.py`:
- **Imports:** `contextlib` and `errno`, and `normalize_path` from `gator_core`.
- **`_fleet_reconciled(fleet, registry)`:** a pure builder that keeps only Fleet repos whose resolved path is still in the registry.
- **Exclusion helpers:**
  - `_REPO_ACTION_GUARD` / `_REPO_ACTION_LOCKS` and `_repo_action_key()`.
  - `_repo_action(repo_path)`: a context manager with a non-blocking acquire that yields True or False.
  - `_resolve_action_target(repo_name, registry, fleet)`: the same lookup as `data.resolve_repo_update`, i.e. the registry by name, else an *accessible* Fleet entry; returns `(path, source)` or `(None, None)`.
  - `_still_targeted(path, source)`: re-checks against fresh snapshots.
- **New constants and lock:** `_REPO_BUSY_ERROR`, `_AUDIT_LOCK`, `_LOOP_BUSY_ERROR`, `_LOOP_LOCK_BUSY_ERRNOS` (`EDEADLK` / `EDEADLOCK`) and `_loop_lock_busy(exc)`.
- **Refresh (`do_GET /api/refresh`):**
  - `_refresh_lock.acquire(blocking=False)` happens in the request thread. When busy, the response is `already_refreshing`.
  - The `dashboard-refresh` worker collects from a snapshot outside the locks, then publishes `_fleet_reconciled(data, _registry_snapshot())` under `_STATE_WRITE_LOCK`. A collection exception becomes a debug print and the old Fleet stays. The worker always releases the lock in `finally`.
  - If `Thread.start()` raises, the route releases the lock and returns 500.
- **`_handle_audit_sessions`:** computes the result under `_AUDIT_LOCK` and responds after release.
- **Register / remove:** both resolve the path, then take `_repo_action` (busy: 409). Their bodies moved unchanged into `_register_owned()` / `_remove_owned()`, keeping checkpoint 1's rule that the response is sent after `_STATE_WRITE_LOCK` is released.
- **Config / topology:** request parsing and validation run as before, then `_resolve_repo_path` (registry only, the same 404 message as before). After that, `_with_repo_action(repo_name, repo_path, "registry", …)` runs the bodies, which moved unchanged into `_config_owned()` / `_topology_owned()`.
- **Update / gatorize:** go through `_lifecycle_action(repo_name, resolve_fn)`:
  - With no target, `resolve_fn` runs on the route's snapshots, and `data.py` gives its usual 400/404.
  - Otherwise `_with_repo_action` calls `resolve_fn` with a one-entry registry `({"name", "path": target},)` and an empty Fleet, so `data.py` (unchanged) can only resolve the locked path.
- **`_with_repo_action()`:** busy gives 409. `_still_targeted` false gives 404 `repo '<name>' not found`, with no side effect. Otherwise it runs `fn()` while the lock is held.
- **Architect Loop actions:** `_handle_loop_pause`, `interject`, `unblock`, `extend`, `reopen` and `end` each gain `except OSError` right after their `PermissionError` branch. `_loop_lock_busy` gives 503 with nothing written; anything else is re-raised (behavior unchanged). The Dashboard still never takes `session.lock` itself.

`data.py` and `updates.py` are unchanged.

## Charter Updates

`.gator/charters/scripts-dashboard.md`:
- **State-helper entry:** the refresh note now describes single-flight admission, worker ownership and `finally` release, reconciliation, failure handling, and the pinning test class.
- **New entry `_repo_action(...) / _REPO_ACTION_LOCKS / _resolve_action_target(...) / _still_targeted(...) / DashboardHandler._with_repo_action() / _lifecycle_action() / _register_owned() / _remove_owned() / _config_owned() / _topology_owned()`:**
  - Purpose and callers.
  - A TRIPWIRE: strict ordering against remove, with no success after a later remove (pinned by `TestRemoveVersusSamePath`).
  - Lock order: `_repo_action` first, the state locks inside, never the reverse; holding it across the subprocess is intended.
  - Loop routes are outside it.
- **New entry `_AUDIT_LOCK`:** why it exists (the aggregator's `_atomic_write`), route-local scope, and response after release.
- **Architect control routes:** a new "Busy" tripwire with the exact `EDEADLK` mapping, the list of covered actions, and other `OSError`s propagating (pinned by `TestLoopRaces`).

Checked: every name in the new headings exists in the file (`grep -n "def _repo_action\|def _resolve_action_target\|def _still_targeted\|def _with_repo_action\|def _lifecycle_action\|def _register_owned\|def _remove_owned\|def _config_owned\|def _topology_owned\|_AUDIT_LOCK =\|_REPO_ACTION_LOCKS ="`).

## Verification

**New tests in `tests/test_dashboard_concurrency.py`** (26 total now, all on the test-local `ThreadingHTTPServer`):

`TestRefreshSingleFlight` (pin 3):
- 10 barrier-synchronized `/api/refresh` calls while the collector is gated: exactly 1 `refreshing` and 9 `already_refreshing`, one collection, readers see the whole old object during it and the new one after, and the next refresh is admitted.
- A remove that lands mid-collection is not undone: reconciliation.
- A failing collection releases admission and keeps the old Fleet.

`TestRemoveVersusSamePath` (pins 4a–4c), with the subprocess (`data.run_text`) and `gator_core` writers gated:
- (a) While update or gatorize is held mid-subprocess, a same-path remove gets 409 and the registry is unchanged. After release, the action reports 200 and the remove then succeeds.
- (b) While a remove is held mid-write, update, gatorize, config and topology each get 409. After the remove, each gets 404, no subprocess call is recorded, and `config.json` is not written.
- An action that resolved its target, then lost it to a completed remove before taking the lock, gets 404 with no subprocess call (the `_still_targeted` re-check).
- (c) While a register is held, a second register and a remove for the same path both get 409. Registry file and snapshot end with exactly one entry.

`TestAuditSerialization`: 6 concurrent audit requests reach a peak concurrency of 1.

`TestLoopRaces` (pin 5):
- Two barrier-synchronized `/extend`: `[200, 409]` (or `[200, 503]`), exactly one `loop_extended` event, `max_rounds` raised once, at most one watcher.
- Two barrier-synchronized `/loops/start`: `[201, 409]` and exactly one loop directory.
- With `session._lock_exclusive` raising `OSError(EDEADLK)`, each of pause, interject, unblock, end and extend returns 503 `{"error": "loop is busy; retry"}` and `session.json` is byte-identical.
- `_loop_lock_busy` accepts only the timeout errno.

Watchers are reaped (`/end` plus a join). A post-run thread listing shows only `MainThread`.

**Base check:** against checkpoint 1's staged `gator-dashboard.py`, **16 fail**: refresh reconciliation; every remove-versus-same-path case (a, b, the re-check, c); audit serialization; all five 503 mappings; and the errno helper. Ten pass, as expected for the two Loop race tests, because the Loop locks already guarded them; these pin that the threaded server keeps that. Not caught on the old code: `test_concurrent_refreshes_admit_one_collection`. Checkpoint 1's `locked()`-then-start race window, between the check and the worker's acquire, is too narrow to hit over HTTP. The test pins the new single-flight behavior, but it did not reproduce the old race. I state that plainly rather than claim it.

**Generation 3 runs:**
- `python -m pytest tests/test_dashboard_concurrency.py`: 28 passed. The real-contention test takes about 10 s.
- `python -m pytest tests/test_dashboard_concurrency.py tests/test_dashboard_loops.py tests/test_dashboard_remove.py tests/test_dashboard_loop_coding.py`: 172 passed, 6 skipped.

**Generation 2 suites (unchanged code paths since then; the revision changed only a comment, the charter and tests):**
- `python -m pytest tests/test_dashboard_remove.py tests/test_dashboard_loops.py tests/test_dashboard_sessions.py tests/test_dashboard_concurrency.py tests/test_dashboard_loop_brief.py tests/test_dashboard_loop_coding.py tests/test_dashboard_loop_liveness.py tests/test_dashboard_loop_attention.py tests/test_dashboard_module_import.py tests/test_snapshot.py tests/test_dashboard_ui/test_harness.py`: **342 passed, 7 skipped** (latest run).
- On the run before that, one failure: `tests/test_dashboard_loop_attention.py::TestListMarker::test_list_attention_notified` with `PermissionError: [WinError 5] Access is denied` on `os.replace(session-*.tmp -> session.json)`. That is Windows refusing to replace a file another handle has open.
- `test_dashboard_loop_attention.py` alone passed 3/3 on this code and 3/3 on `HEAD`'s code, and the full combined rerun passed. That file was not in checkpoint 1's runs, so I have no earlier baseline for it in the combined set.
- The failing test seeds a session and calls `/loops`, a read route. This checkpoint changes no Loop read path. I report it as an intermittent Windows file-sharing failure of unconfirmed cause.

**Staged residue:** the previous commit's session snippet, as in checkpoint 1. `commit_draft.md` gained a checkpoint 2 line in the working tree; it is not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 4) — Mutation admission |
| Checkpoint base tree | `4841e1730af784d2c34b942a302e2d89578afdb1` |
| Generation | 3 |
| Staged tree (candidate) | `42ed56931b0b7c4f9d7bb21521c4b66813985b6c` |
| Changed paths in this checkpoint | 3 (M 3) |
| Loop base HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` |
| Loop base tree | `d42cac773e52d72e9734ad639ce30f744ce5b97a` |
| Current HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` (dev) |
| Changed paths vs loop base (cumulative) | 5 |
| Unstaged / untracked residue | 1 other + 20 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 4841e1730af784d2c34b942a302e2d89578afdb1 42ed56931b0b7c4f9d7bb21521c4b66813985b6c
```

Cumulative context (approved checkpoints plus this one): `git diff d42cac773e52d72e9734ad639ce30f744ce5b97a 42ed56931b0b7c4f9d7bb21521c4b66813985b6c`.

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

Loop residue: 20 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
