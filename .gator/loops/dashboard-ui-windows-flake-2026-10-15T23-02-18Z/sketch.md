---
date: 2026-10-15
type: implementation-sketch
issue: 70
feature: dashboard-ui-windows-flake-diagnosis-and-readiness
recommended-path: diagnostic-slice-before-concurrency-change
---

# #70 — Windows Dashboard UI Flakes: Diagnosis and Shared Readiness Sketch

## Executive Summary

- The failures move among unrelated Playwright tests and occur only on
  `windows-latest · py3.12`; the shared harness or browser-ready boundary is
  the leading suspect, not each failed assertion.
- The harness already allows 45 seconds for the Dashboard process to print its
  `Ready on <url>` line. The observed 15-second failures happen later, while a
  browser is waiting for a rendered view such as `.repo-file-item`.
- First make the next failure explain itself: retain Playwright artifacts and
  emit a small, structured browser/server diagnostic bundle.
- Then replace scattered rendered-DOM waits with one meaningful readiness
  contract. Do not increase timeouts, add automatic reruns, or change the
  Dashboard to a threaded HTTP server without evidence that request queueing
  is the cause.

## Problem and Evidence

The Windows `dashboard-ui` source-CI job failed nine times across eight tests
between 2026-09-15 and 2026-10-09, while the corresponding Ubuntu job passed.
The individual failures span responsive shell, Loop workspace, Loop liveness,
Loop Markdown, and Fleet/file-tree paths. A moving target like this is strong
evidence for a shared race or cold-runner readiness problem.

The useful concrete observation is the 2026-10-09 failure: Playwright waited
15 seconds for `.repo-file-item` to become visible, while that locator had
already resolved 132 elements. That does not identify whether the browser was
on the wrong view, the view was hidden, a request was delayed, JavaScript
failed, or the server was blocked. It does show that simply extending a test's
timeout would hide the missing diagnosis.

The existing harness is not careless about process startup:

- `build_dashboard_fleet()` starts a real Dashboard child with an isolated
  home and registry.
- `read_ready_url()` waits up to 45 seconds for its stdout ready protocol and
  includes stdout/stderr if startup fails.
- Page tests commonly call `page.goto(..., wait_until="load")` and then each
  perform their own 10- or 15-second selector wait.

Therefore the suspected boundary is **Dashboard rendered and usable in this
browser**, not merely **the Python process bound a loopback port**.

## Non-goals

- Do not blanket-increase per-test timeouts.
- Do not add `pytest-rerunfailures` or silently retry CI jobs.
- Do not turn `HTTPServer` into `ThreadingHTTPServer` as a speculative fix.
- Do not weaken the isolation of the real child-process harness or replace it
  with mocks.
- Do not make the suite pass by dropping its long-Fleet or Loop coverage.

## Constraints and Existing Contracts

The Dashboard currently uses one loopback `HTTPServer`. Its background threads
are narrow, intentional ownership domains: loop host/watchers and a few
long-running lifecycle actions. Loop watcher attachment has its own lock and
registry invariants. A broad server-concurrency change would create shared-state
and lifecycle risks across the very surfaces this suite exercises.

The UI deliberately has asynchronous rendering and live polling. In particular,
the Loop workspace preserves the last valid display when refresh fails. A
readiness helper must wait for a positive, view-specific condition; it must not
reinterpret a transient error or empty display as a healthy state.

The CI job has a 20-minute ceiling. It currently runs the whole Dashboard UI
suite in one invocation and publishes no browser artifacts on failure.

## Recommended Delivery Sequence

### Slice 1 — Make failures attributable

1. Configure Playwright to retain a trace and screenshot on failure. Retain
   video only if its storage and upload cost is acceptable after one trial.
   Keep successful runs artifact-free.
2. Add a failure-only CI upload step for the Playwright output directory. Name
   artifacts with operating system, Python version, run attempt, and commit
   SHA. Upload even if the test process has already failed.
3. Add a small diagnostic fixture/helper that, on test failure, records:

   - current URL and page title;
   - viewport dimensions;
   - browser console messages and uncaught page errors captured during the
     test;
   - a bounded DOM/state snapshot: visible view, selected repository key,
     selected sidebar item, and counts plus visibility of the principal view
     roots; and
   - Dashboard child PID, return code, and bounded recent stdout/stderr.

   This must be diagnostic-only. It must not make browser requests, mutate the
   Dashboard, or introduce another timing dependency during ordinary passing
   tests.
4. Make the diagnostic bundle safe to publish: test data is synthetic, but
   trim output to a bounded size and never capture host environment values or
   arbitrary file content.

**Exit condition:** the next Windows failure identifies which class occurred:
server exited, navigation/view-selection mismatch, browser JavaScript error,
network/request delay, or a DOM/layout visibility problem.

### Slice 2 — Establish one shared rendered-ready contract

After Slice 1 confirms the broad failure class, introduce a helper with a name
and contract such as `open_repo_when_ready(page, fleet, repo="alpha")`.

It should:

1. Navigate to the exact repository URL.
2. Confirm the initial response/navigation completed.
3. Wait for the repository view's explicit ready signal: correct selected repo
   identity plus an attached, visible repository content root. It must use a
   selector specific enough to prove the requested repository mounted, not a
   count of generic elements elsewhere in the document.
4. On timeout, fail with the same bounded diagnostic state from Slice 1.

Migrate the repeated `goto(... ?repo=alpha)` plus `.repo-file-item` patterns
first. Keep test-local waits where the test is asserting a later user action;
the helper is for setup/readiness, not a universal synchronization hammer.

If the ready condition exposes a product-side ambiguity—for example, a view
root says it is mounted before its file-tree request resolves—add a small,
semantically named DOM readiness marker owned by the Dashboard UI. Test the
marker's lifecycle directly. Do not rely on arbitrary sleeps.

**Exit condition:** a representative Windows stress run shows the shared helper
is stable, and at least the historically failing file-tree and Loop paths use
the same contract.

### Slice 3 — Fix the proven cause

Choose one branch only after the artifacts identify it:

| Evidence | Targeted response |
|---|---|
| Child process exited or has an exception | Repair Dashboard startup/request error handling; retain child-output reporting. |
| Browser console/page error | Fix the UI race or exception and pin the error-free render path. |
| Navigation lands on Welcome/Fleet instead of requested Repo view | Repair route/state initialization and add a focused navigation regression test. |
| Repo view mounts but its data request is delayed/failed | Repair the API/harness readiness dependency; distinguish an unavailable response from an empty file tree. |
| Requests demonstrably queue behind a slow synchronous handler | Profile the handler first. Consider a bounded concurrency design only with explicit shared-state and shutdown tests. |
| Visibility/layout only | Repair the view/root visibility contract and retain a narrow viewport test. |

## Validation Plan

1. Run the affected test modules locally on Windows before and after each
   slice, preserving a failing bundle when possible.
2. Run a bounded repeated Windows stress pass of a mixed selection: one
   responsive-shell test, one file-tree test, one Loop workspace test, and one
   Loop liveness test. The purpose is to exercise the shared fixture repeatedly,
   not to manufacture per-test retries in CI.
3. Run the full `tests/test_dashboard_ui/` suite on Windows and Ubuntu.
4. Verify failure artifacts upload only on failure and that a deliberate,
   locally induced diagnostic failure produces readable output.
5. After the fix ships, monitor several normal Windows source-CI runs before
   closing #70. A single rerun passing is not evidence that an intermittent
   flake is resolved.

## Likely Files

- `.github/workflows/source-ci.yml` — failure-only artifact retention.
- `tests/test_dashboard_ui/conftest.py` — scoped failure diagnostics and/or
  reusable page-ready fixture.
- `tests/test_dashboard_ui/_harness.py` — bounded access to the Dashboard
  child output and shared readiness helpers.
- A limited set of UI test modules that currently reproduce navigation plus
  `.repo-file-item` waits.
- `src/gator_command/scripts/dashboard/*.js` only if investigation proves the
  current DOM does not express a truthful mounted/ready state.

## Decision Record

The first implementation should be diagnostic and harness-centered. A
threaded-server change is deferred until retained traces and process/browser
diagnostics demonstrate head-of-line blocking in the existing server. That is
not the evidence presently available.

## Connections

- GitHub issue #70 — source-CI Windows Dashboard UI flake record.
- `.gator/charters/scripts-dashboard.md` — server lifecycle and loop watcher
  ownership boundaries.
- `.gator/charters/scripts-dashboard-ui.md` — UI polling, refresh-failure,
  and mounted-workspace invariants.
- `tests/test_dashboard_ui/_harness.py` — real Dashboard child, ready protocol,
  seeded repositories, and Fleet-opening helper.
- `.github/workflows/source-ci.yml` — Dashboard UI job and timeout boundary.
