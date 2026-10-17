# Implementation: Dashboard Threaded Request Server — Checkpoint 4 (Threaded server)

## Executive Summary

- `main()` now serves with `DashboardHTTPServer` (`ThreadingMixIn` + `HTTPServer`): one daemon worker per request, at most `MAX_WORKERS` (16). Excess connections queue in the listen backlog.
- Expensive routes share `HEAVY_WORKERS` (4) slots, with 503 "dashboard busy; retry" after 60 s, so small reads always have workers.
- The browser-level proof reproduces the original #70 symptom. With only the server class reverted to `HTTPServer`, the document request never answers while a listing is held, and Playwright times out after 8 s. With the threaded server, the document frame loads during the held listing.
- Performance on this repository: one `/files` listing takes 2.95 s. A small `/file` takes 4 ms idle and 8 ms (11 ms max) while 4 listings run. 4 concurrent listings take 7.3 s wall versus about 11.8 s serial.

## Implementation Summary

`src/gator_command/scripts/gator-dashboard.py`:
- **Imports:** `socketserver`.
- **New constants:** `MAX_WORKERS = 16`, `HEAVY_WORKERS = 4`, `_HEAVY_TIMEOUT = 60.0`, `_HEAVY_SLOTS` (a `BoundedSemaphore`), `_HEAVY_BUSY_ERROR`.
- **`_heavy_work()`:** a context manager that yields True holding a slot, or False after the timeout. It reads `_HEAVY_SLOTS` at call time.
- **`DashboardHTTPServer`:**
  - Class attributes: `daemon_threads = True`, `block_on_close = False`, `request_queue_size = 64`.
  - `__init__(…, max_workers=MAX_WORKERS)` creates a per-server `BoundedSemaphore`.
  - `process_request` takes a slot (blocking), then starts a `dashboard-request` daemon thread. If the start fails, it releases the slot and calls `shutdown_request`.
  - `process_request_thread` wraps the mixin's version and releases the slot in `finally`.
- **`DashboardHandler._send_heavy_busy(cache_control=None)`:** sends 503 `{"error": "dashboard busy; retry"}`.
- **Heavy wrapping:**
  - In the parse-once dispatch, `files` and per-file `history` (`no-store` on a versioned request, matching the handlers).
  - In the legacy `do_GET` branches, by a mechanical re-indent with no logic change inside: `/api/audit/sessions` (the slot is taken before `_AUDIT_LOCK`), repo-scope `/history`, `/search`, `/check`, `/commits`, Tier-2 `/api/repo/<name>`, `/api/repos/discover`.
  - `/file`, `/raw`, `/api/data`, Welcome documents, static assets and every Loop route are **not** heavy.
- **`_debug_files_gate_wait()`:** called first in `_handle_files`. It does nothing unless `GATOR_DASHBOARD_DEBUG=1` **and** `GATOR_DASHBOARD_DEBUG_FILES_GATE=<path>` are set; then it waits up to 30 s for that file to exist.
- **`main()`:** constructs `DashboardHTTPServer` on both bind paths (port 0 and a fixed port). The `Ready on` line, the loopback bind and `serve_forever` are unchanged.
- **Unchanged on purpose:** `protocol_version` stays HTTP/1.0.

## Charter Updates

- `.gator/charters/scripts-dashboard.md`:
  - **New entry** `DashboardHTTPServer / MAX_WORKERS / HEAVY_WORKERS / _HEAVY_SLOTS / _HEAVY_TIMEOUT / _heavy_work() / DashboardHandler._send_heavy_busy()`. It covers admission (backlog queueing, slot release, start failure), the heavy/not-heavy route lists, and these tripwires:
    - HTTP/1.0, because keep-alive would pin workers;
    - where the cap values come from, and the instruction to re-measure;
    - "every request is concurrent", with the full lock order: `_LifecycleGate`, then `_heavy_work` / `_AUDIT_LOCK` / `_repo_action`, then `_STATE_WRITE_LOCK`, then `_STATE_LOCK`, with Loop OS locks never taken under a state lock;
    - a slot is held while the response is written.
    It also names the pinning tests.
  - `main()`: serves with `DashboardHTTPServer` on both bind paths.
  - `DashboardHandler.do_GET() / do_POST()`: the debug files-gate seam and its two-variable rule.
- `.gator/charters/scripts-cross-cutting.md`, Loop lock paragraph: the Dashboard serves concurrently, never holds its state locks while acquiring a Loop OS lock, keeps `_LOOP_HOSTS_LOCK` a leaf, and the Loop locks stay the only authority for transitions.
- `.gator/charters/scripts-dashboard-ui.md`: unchanged, because there is no browser code change. The new UI test is named in the server charter's pinned-by line.

Checked by grep: every new heading name exists in the file, and `HTTPServer((` no longer appears in `main()` except as `DashboardHTTPServer((` (also pinned by a test).

## Verification

**New tests in `tests/test_dashboard_concurrency.py`** (41 in the module). These use the real `DashboardHTTPServer` through `threaded(…, production=True)`. A new `_request_full()` returns headers.

`TestThreadedServer`:
- `test_slow_listing_does_not_block_document_reads` (**pin 1**): a real `/files` handler is held inside `_iter_scanner_files`. `/file/artifacts/marker-alpha.md` and the HTML `/raw/artifacts/page.html` each return 200 in under 2 s. The listing then completes.
- `test_worker_cap_queues_excess_requests`: with `max_workers=2` and two held listings, a third request waits, exactly 2 `dashboard-request` threads exist, and it is served after release.
- `test_heavy_routes_share_a_bounded_pool`: with one heavy slot and a 0.5 s bound, `/search` gets 503 `dashboard busy; retry` while a listing holds the slot. `/file` still returns 200, and `/search` returns 200 after release.
- `test_main_serves_with_the_threaded_server`: `main()` builds `DashboardHTTPServer` twice and no bare `HTTPServer`, and `protocol_version` is HTTP/1.0.

`TestConcurrentReads::test_mixed_reads_across_two_repositories` (**pin 2**): 40 iterations over 8 workers, each doing `/files`, `/raw` HTML, Loop `/status` and `/api/data` for one of two repos. It checks identity markers, `nosniff`, the CSP with `frame-ancestors`, and `Vary: Sec-Fetch-Dest`.

`TestContentPolicyUnderConcurrency` (**pin 7**, subset): 10 negative requests, each hitting a different check (verified serially):
- 400: encoded separator, traversal;
- 404 no-oracle: `.git/config`, an existing override file versus a missing file (identical 404);
- 400: reserved name `CON.md`, trailing dot, unknown repo, malformed version.
Run 8 times each with 16-way concurrency, every answer is byte-identical to the serial one.

`TestMixedStress` (**pin 8**): 400 mixed requests over 12 threads, covering reads, register/remove churn, refresh (collector stubbed), config POST and Loop status. It finished in under 90 s with no unexpected status, no crossed identity, and on failure it reports diagnostics (threads and problems). End state: registry file equals snapshot, seeded repos present, `config.json` correct. No automatic rerun.

**New `tests/test_dashboard_ui/test_request_concurrency_ui.py`** (browser level). It uses its own fleet, with `GATOR_DASHBOARD_DEBUG_FILES_GATE` set for the dashboard process.
- Flow: open alpha, wait for the default document, then select `blueprints/plain.html` (the frame loads). Go to beta, close the gate, return to alpha.
- The cached-tree return starts alpha's `/files`, which is held. Meanwhile `/raw/blueprints/plain.html` answers 200 and the frame finishes loading, with no `/files` response yet. Reopening the gate completes the listing.
- **Base checks:**
  - on checkpoint 3's code plus only the gate seam: fails (`Timeout 8000ms … waiting for event "response"`);
  - on this candidate with only `main()`'s port-0 server class reverted to `HTTPServer`: fails the same way;
  - on this candidate: passes.
- **Stabilized during this checkpoint.** In the full UI run the first version failed once, because it picked whichever HTML file came first (`blueprints/shipped/_template-narrative.html`). In `test_repo_tree_cache.py` + this file order, it also sometimes clicked before the default document had loaded, and no frame appeared. The test now pins `blueprints/plain.html` and waits for the default document first. It passed 3/3 in that order and alone.
- **Observation for the Architect (pre-existing, not changed here):** clicking an HTML file while the repository's default document is still loading can leave no frame. That looks like the default load's late response overwriting the newer selection in `views/repo.js`. It is a browser-side ordering issue outside this checkpoint's scope and worth a separate note.

**Performance record** (`scratchpad/perf_check.py`; in-process `DashboardHTTPServer` over this repository, warm cache, Windows 10, Python 3.13):
- 1 `/files` listing: median 2.95 s (2.95 / 3.00 / 2.91).
- 2 concurrent listings: 4.42 s wall. 4 concurrent: 7.26 s wall, each about 7.2 s. Listings are CPU/GIL-bound, so concurrency gives about 1.6× throughput and each listing gets slower.
- Small `/file` (`charters/INDEX.md`): 4 ms idle; **8 ms median, 11 ms max during 4 listings**.
- Conclusion: `HEAVY_WORKERS = 4` meets the responsiveness goal. Per-listing cost stays visible (2.95 s), so threading does not hide it. Listing optimization remains separate work.

**Suites:**
- `tests/test_dashboard_ui/` plus all backend Dashboard suites (`tests/test_dashboard_remove.py tests/test_dashboard_loops.py tests/test_dashboard_sessions.py tests/test_dashboard_concurrency.py tests/test_dashboard_loop_brief.py tests/test_dashboard_loop_coding.py tests/test_dashboard_loop_liveness.py tests/test_dashboard_loop_attention.py tests/test_dashboard_module_import.py tests/test_snapshot.py tests/test_welcome_docs.py`): **877 passed, 17 skipped, 1 failed** in 16 min 45 s. The one failure was the first version of the new UI test, now stabilized as described above.
- The full `tests/test_dashboard_ui/` rerun with the stabilized test: **524 passed, 11 skipped, 0 failed** (12 min 6 s), with `test_request_concurrency_ui.py` included in its normal position.

Known gaps: Linux CI has not been run from here (this machine is Windows). The Windows-only real-lock test from checkpoint 2 is skipped elsewhere by design. #70 is not claimed closed.

Staged residue: the previous commit's session snippet, as before. `commit_draft.md` gained a checkpoint 4 line in the working tree; it is not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp4 (4 of 4) — Threaded server |
| Checkpoint base tree | `0e4a0bf713328ab5eba97e0f73e1c947f51d11a8` |
| Generation | 6 |
| Staged tree (candidate) | `89abc0eb0d323f2f642e3d1d186e93213634ae90` |
| Changed paths in this checkpoint | 5 (A 1, M 4) |
| Loop base HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` |
| Loop base tree | `d42cac773e52d72e9734ad639ce30f744ce5b97a` |
| Current HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` (dev) |
| Changed paths vs loop base (cumulative) | 7 |
| Unstaged / untracked residue | 1 other + 26 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 0e4a0bf713328ab5eba97e0f73e1c947f51d11a8 89abc0eb0d323f2f642e3d1d186e93213634ae90
```

Cumulative context (approved checkpoints plus this one): `git diff d42cac773e52d72e9734ad639ce30f744ce5b97a 89abc0eb0d323f2f642e3d1d186e93213634ae90`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-cross-cutting.md
M .gator/charters/scripts-dashboard.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/gator-dashboard.py  [revisits an earlier checkpoint]
M tests/test_dashboard_concurrency.py  [revisits an earlier checkpoint]
A tests/test_dashboard_ui/test_request_concurrency_ui.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 26 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
