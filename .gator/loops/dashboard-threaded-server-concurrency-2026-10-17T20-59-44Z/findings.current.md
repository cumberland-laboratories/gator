# Review: Dashboard Threaded Request Server — Checkpoint 4

## Executive Summary

- The staged candidate replaces the single-request dashboard listener with a bounded `DashboardHTTPServer`, preserving HTTP/1.0 so idle keep-alive connections cannot consume worker capacity.
- Worker admission is bounded to 16 daemon request threads, while expensive routes share four independently bounded slots; queueing, startup failure cleanup, and slot release are all explicit.
- Heavy-route wrapping covers listings, history, search, status/subprocess work, discovery, and audit while leaving documents, raw content, data, static assets, and Loop routes responsive.
- The backend and browser-level tests directly exercise the original head-of-line scenario; the Dashboard and cross-cutting charters record the new concurrency and lock-order contracts.

## Verdict

APPROVE

## Findings

No blocking findings.

## Scope Check

The exact checkpoint diff from `0e4a0bf713328ab5eba97e0f73e1c947f51d11a8` to staged tree `89abc0eb0d323f2f642e3d1d186e93213634ae90` is limited to the threaded server, bounded heavy-work admission, concurrency coverage including the browser proof, and the corresponding Dashboard and cross-cutting charter updates. It is consistent with the approved Threaded server checkpoint.

## What Looks Good

- `DashboardHTTPServer.process_request_thread()` releases its per-server worker slot in `finally`; failure to start the thread releases the slot and closes the request.
- `_heavy_work()` consults its semaphore at call time, which keeps the test seam sound, releases each acquired slot in `finally`, and yields the documented 503 response after the bounded wait.
- `tests/test_dashboard_concurrency.py` passes in full using a workspace-local pytest base: **41 passed in 38.51s**. The focused production-server, cross-repository/content-policy, and mixed-stress subset also passed: **7 passed**.
- The candidate retains the existing response and content-policy behavior under concurrent load, and the new Playwright test ties the fix to a real document-load scenario.

## Reviewed Candidate

<!-- Captured by the gator loop CLI at review submission. -->

| Fact | Value |
|---|---|
| Verdict | APPROVE |
| Reviewed staged tree | `89abc0eb0d323f2f642e3d1d186e93213634ae90` |
| Reviewed HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` |
| Candidate round | 3 |
| Checkpoint | cp4 (4 of 4) — Threaded server |
| Checkpoint base tree | `0e4a0bf713328ab5eba97e0f73e1c947f51d11a8` |
| Generation | 6 |
| Live candidate unchanged at review | yes |
