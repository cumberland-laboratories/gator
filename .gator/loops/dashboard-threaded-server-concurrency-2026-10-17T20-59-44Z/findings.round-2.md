# Review: Dashboard Threaded Request Server — Checkpoint 2

## Executive Summary

- REVISE: lifecycle exclusion, refresh publication, and audit serialization are comprehensively designed and tested.
- The Loop busy mapping narrows the Windows session-lock timeout to `EDEADLK` without establishing that this is the error produced by `msvcrt.locking(..., LK_LOCK, 1)` on the supported Windows runtime.
- The plan requires the actual session-lock acquisition timeout to become the retryable 503; other I/O errors must still surface normally.
- Replace the guessed errno classification with an evidenced, dedicated lock-contention boundary and cover the real Windows path.

## Verdict

REVISE

Checkpoint 2 is not ready while its claimed Windows retry behavior is pinned only to a synthetic errno that may not be the one emitted by the session lock implementation.

## Findings

### Finding 1: The Loop busy mapping is not tied to the actual Windows lock-timeout signal

**Severity**: High

**Location**: `src/gator_command/scripts/gator-dashboard.py`, `_LOOP_LOCK_BUSY_ERRNOS` / `_loop_lock_busy()` and the new `except OSError` branches for Architect Loop actions; `tests/test_dashboard_concurrency.py::TestLoopRaces`.

**Issue**: The candidate maps only `OSError.errno in {EDEADLK, EDEADLOCK}` to 503. The underlying Windows `session._lock_exclusive()` is a direct `msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)` call, whose documented failure is simply `OSError` after retrying; this checkpoint does not establish that its contention failure carries `EDEADLK`. The tests inject `EDEADLK`, so they prove only the new classifier, not the Windows behavior the plan promises. A real contention error with a different errno will be re-raised and drop the Dashboard response instead of returning `{"error": "loop is busy; retry"}`.

**Suggestion**: Make the session-lock contention outcome explicit at the narrow lock boundary (for example, a dedicated exception or a verified platform-specific classifier in the Loop lock helper), then have the Dashboard map only that outcome to 503 while retaining propagation for unrelated I/O faults. Add a test that exercises the actual Windows lock-contention behavior or a platform-bound helper contract, plus a non-contention `OSError` regression case. Update the charter to name that proven boundary rather than asserting an unverified errno.

## Scope Check

The candidate remains within the approved mutation-admission checkpoint and its Context/charter work is appropriate. This finding enforces the sketch’s required honest error behavior for racing Loop operations and does not broaden the feature.

## What Looks Good

- Same-path register/remove/update/gatorize/config/topology ordering is explicit and well covered.
- Refresh admission now has a non-racy acquire and exception-safe release, with reconciliation against removals.
- Audit-session aggregation is serialized without holding the lock during response output.

## Reviewed Candidate

<!-- Captured by the gator loop CLI at review submission. -->

| Fact | Value |
|---|---|
| Verdict | REVISE |
| Reviewed staged tree | `37e89c1e20e9d2f10a56217a5ea8c8f3979dc007` |
| Reviewed HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` |
| Candidate round | 1 |
| Checkpoint | cp2 (2 of 4) — Mutation admission |
| Checkpoint base tree | `4841e1730af784d2c34b942a302e2d89578afdb1` |
| Generation | 2 |
| Live candidate unchanged at review | yes |
