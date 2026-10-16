# Implementation Plan: #70 — Windows Dashboard UI flakes, diagnosis and shared readiness

## Executive Summary

- Implements the sketch's Slices 1 and 2. Slice 1 makes the next Windows failure attributable: the CI job keeps Playwright traces and screenshots, but only on failure. A failure-only diagnostic bundle records browser state and bounded output from the Dashboard child process.
- Slice 2 adds one shared readiness helper, `open_repo_when_ready()`. It waits for a positive, repository-specific condition and replaces the 12 repeated `goto(?repo=alpha)` + `.repo-file-item` setup waits.
- Slice 3, the cause fix, is deliberately not planned. The sketch says its branch is chosen only after the new artifacts identify the failure class.
- No timeout increases, no reruns and no server-concurrency change. Verification uses focused harness tests, a deliberately induced failure, a bounded Windows stress pass, and the full suite on Windows and Ubuntu.

## Summary

The Windows `dashboard-ui` lane fails intermittently, on a different test each time. The suspected boundary is "Dashboard rendered and usable in this browser", not "the child process bound its port". The sketch also says not to fix anything before a failure can explain itself. This plan therefore first adds failure-only evidence: Playwright traces and screenshots, a structured browser/server bundle, and a CI upload. It then replaces the copied setup waits with one readiness contract that proves the requested repository mounted. That contract fails with the same diagnostics.

## Context Checked

- Architect brief: none listed by `gator loop status` (no `architect-brief.md` in the loop directory).
- `sketch.md` (scope, non-goals, constraints, recommended sequence, likely files).
- `.gator/charters/INDEX.md`: `.github/workflows/**` maps to Release Pipeline + Cross-Cutting. `tests/**` has no charter mapping.
- `.gator/charters/release-pipeline.md` "Workflow A: Source CI": least-privilege, immutable or major-version action pins, the workflow-linter rule, and the `dashboard-ui` 20-minute timeout tripwire.
- `.gator/charters/scripts-dashboard-ui.md`:
  - `navigate() / showView() / setActiveRepo()`: the `?repo=<name>` landing contract, the "▸ <name>" Repo label, and URL/visible-selection synchronization.
  - `renderRepo() / loadFileList()`.
- `tests/test_dashboard_ui/_harness.py`: `build_dashboard_fleet()`, `read_ready_url()` (45 s ready protocol), `spawn_reader_thread()`, `drain_queue()`, `open_fleet()`.
- `tests/test_dashboard_ui/conftest.py`: session/function fleet fixtures, page fixtures, lifecycle probe.
- `.github/workflows/source-ci.yml`: the `dashboard-ui` job (matrix ubuntu/windows, single `pytest tests/test_dashboard_ui/ -v --tb=short` step, no artifact upload).
- Call sites grepped: the `goto(... "?repo=alpha", wait_until="load")` + `wait_for_selector(".repo-file-item", timeout=15000)` pair appears in:
  - `test_docs_view.py`;
  - `test_loop_workspace.py` (lines 61, 387, 1295, 3032, plus `_navigate_to_loop()`);
  - `test_responsive_shell.py` (lines 169, 631, 680, 753, 812);
  - `test_welcome_ui.py` (line 124).
  - `test_harness.py:222` navigates without that wait and is not migrated (see Change 6).
- `views/repo.js`: `.repo-file-item` buttons are emitted per tree node (`data-path`), including inside collapsible directories.
- `pyproject.toml`: `pytest-playwright` is already a dev dependency.

## Approach

**Evidence before fixes (sketch Slice 1).** Use pytest-playwright's built-in failure retention (`--tracing retain-on-failure`, `--screenshot only-on-failure`, `--output`). Video stays off; the sketch allows it only after one trial. Add a repository-owned diagnostic bundle for what a trace does not hold well:
- Dashboard child PID, return code, and recent stdout/stderr;
- a compact JSON summary of the visible view, the selected repository, and view-root counts and visibility.

The bundle is written only on test failure. On a passing test it does nothing beyond attaching two in-memory event listeners. It makes no network requests and does not mutate the Dashboard.

**One readiness contract (sketch Slice 2).** `open_repo_when_ready(page, fleet, repo="alpha")` navigates to the exact URL and checks the navigation response. It then waits on a single `wait_for_function` predicate that must all be true together:
- `#view-slot` carries `route-repo`;
- the shell's Repo label names the requested repository (`setActiveRepo` sets it);
- at least one `.repo-file-item` **inside `#view-slot`** is visible.

The predicate tests "any visible", not "the first match". The 2026-10-09 failure ("resolved to 132 elements", then waited 15 s for visibility) is consistent with the first matching item being hidden, for example inside a collapsed directory. This is noted as a hypothesis only; Slice 1's artifacts decide it. On timeout, the helper raises with the Slice 1 bundle inline.

**Not in this plan:** Slice 3. The sketch makes the cause fix conditional on evidence this plan produces. Picking a branch now would be the speculative fix the sketch forbids. A follow-up loop owns it.

## Changes

### 1. CI: keep Playwright failure artifacts and upload them on failure only
- File: `.github/workflows/source-ci.yml` (`dashboard-ui` job only)
- What:
  - Change the run step to `python -m pytest tests/test_dashboard_ui/ -v --tb=short --tracing retain-on-failure --screenshot only-on-failure --output test-results/dashboard-ui`.
  - Add a step `if: failure()` using `actions/upload-artifact@v4` (major-version pin, matching the repository's action-pin policy in Release Pipeline). Settings: `name: dashboard-ui-${{ matrix.os }}-py3.12-attempt${{ github.run_attempt }}-${{ github.sha }}`, `path: test-results/dashboard-ui/`, `if-no-files-found: ignore`, `retention-days: 14`.
  - No new permissions: upload-artifact needs none beyond the default token.
- Why: Slice 1 items 1–2. Successful runs upload nothing.

### 2. Harness: keep bounded child output after readiness
- File: `tests/test_dashboard_ui/_harness.py`
- What:
  - Add `_BoundedTail`, a thread-safe `collections.deque(maxlen=200)` of lines.
  - `spawn_reader_thread()` gains an optional `tail` argument and appends to it as well as the queue. `read_ready_url()` keeps its queue contract unchanged.
  - `build_dashboard_fleet()` creates two tails and adds `"server": {"proc": proc, "stdout_tail": ..., "stderr_tail": ...}` to the yielded dict.
  - Add `server_diagnostics(fleet)`, which returns `{pid, returncode (proc.poll()), stdout_tail, stderr_tail}`. Each tail is trimmed to the last 200 lines and 16 KB.
- Why: Slice 1 item 3, the child process part. Today the readers keep enqueueing after `Ready on`, but nothing reads the queues, so post-ready output is lost.
- Teardown (`terminate_and_wait`, thread joins, stream close, registry-isolation asserts) is unchanged. The lifecycle probe keeps passing.

### 3. Harness: browser state snapshot
- File: `tests/test_dashboard_ui/_harness.py`
- What: add `browser_diagnostics(page)`. It returns a dict with:
  - `url` and `title`;
  - `viewport`;
  - one `page.evaluate` snapshot, wrapped in try/except, with a 5 s timeout. It reads:
    - the `#view-slot` class list;
    - the active `.sidebar-item` `data-view`;
    - the Repo label text;
    - counts plus visible counts for `.repo-file-item`, `.fleet-table`, `#loop-sidebar-nav`, `.loop-status-header`, and `.welcome` roots;
    - `document.readyState`.

  If the page or browser is gone, the snapshot records an error string.
- Why: Slice 1 item 3, the DOM/state part. It reads only, makes no fetch, and changes no state.

### 4. Fixtures: failure-only diagnostic bundle
- File: `tests/test_dashboard_ui/conftest.py`
- What:
  - Add a `pytest_runtest_makereport` hookwrapper. It stores each phase's report on `item` (`item.rep_call`, `item.rep_setup`).
  - Add an autouse function fixture, `_ui_failure_diagnostics(request)`. It acts only when the test requested `page`, via `request.fixturenames`. It never forces `page`, so non-browser tests in this directory stay browser-free.
    - It attaches `page.on("console")` and `page.on("pageerror")` listeners into bounded lists (last 100 entries, each truncated to 500 characters).
    - On teardown, if setup or call failed, it writes `<output>/<sanitized nodeid>/gator-diagnostics.json`. The file holds `browser_diagnostics(page)`, the console and page errors, and `server_diagnostics(fleet)` for whichever fleet fixture the test used (`dashboard_fleet`, `dashboard_fleet_mutable`, `dashboard_fleet_debug_off`; looked up with `request.getfixturevalue` only when already in `fixturenames`).
    - `<output>` comes from pytest-playwright's `--output` option (default `test-results`).
  - The file is never written on pass.
  - No host environment values are recorded. The fleet env copy is never serialized, only the PID, return code and tails. File contents are never read.
- Why: Slice 1 items 3–4. The output lands inside the uploaded directory.

### 5. Shared readiness helper
- File: `tests/test_dashboard_ui/_harness.py`
- What: add `open_repo_when_ready(page, fleet, repo="alpha", timeout=15000)`. It:
  1. `resp = page.goto(origin + "?repo=" + repo, wait_until="load")`, then asserts `resp is not None and resp.ok`.
  2. Runs `page.wait_for_function(PREDICATE, arg=repo, timeout=timeout)`, with the predicate as described in Approach.
  3. On `TimeoutError`, re-raises `AssertionError` with `json.dumps(browser_diagnostics(page) + server_diagnostics(fleet))`, bounded.
  4. Returns `page`.

  The timeout stays 15 s, the same value the call sites use now. It is not increased.
- Why: Slice 2 items 1–4. It is setup and readiness only; test-local waits for later user actions stay where they are.

### 6. Migrate the repeated setup waits
- Files: `test_loop_workspace.py` (`_navigate_to_loop()` plus the four inline sites), `test_responsive_shell.py` (169, 631, 680, 753, 812), `test_docs_view.py:100`, `test_welcome_ui.py:124`.
- What: replace the `goto` + `.repo-file-item` pair with `open_repo_when_ready(page, fleet)`. The surrounding test bodies and assertions are unchanged.
- Not migrated:
  - `test_responsive_shell.py:454` deliberately asserts the pre-fetch state.
  - `test_harness.py:222` asserts `_treeState` population itself.
  - Loop helpers in `test_loop_liveness_ui.py`, `test_loop_markdown_ui.py`, `test_loop_brief_ui.py`, `test_loop_coding_ui.py` and `test_loop_refresh_ui.py` that route through `_navigate_to_loop()` inherit the helper automatically. Any that inline their own pair are migrated the same way; the coding loop greps the exact list again before editing.
- Why: Slice 2's migration rule and exit condition ("historically failing file-tree and Loop paths use the same contract").

## Dependencies and Ordering

Change 1 is independent. Changes 2 and 3 come before Change 4, which consumes them. Change 5 depends on 2 and 3 for its timeout message. Change 6 depends on 5. No product code changes.

## Assumptions, Risks, and Required Architect Decisions

- **Non-blocking assumption: Slice 2 ships in the same change as Slice 1.** The sketch says Slice 2 comes "after Slice 1 confirms the broad failure class". This plan assumes the readiness contract does not depend on the failure class:
  - it waits for a truthful positive condition and fails with diagnostics;
  - it does not change product behavior or timeouts.

  Checkpoint 3 is separable. If the Architect wants Windows evidence before the migration, the coding loop stops after checkpoint 2, and checkpoint 3 runs after one failed Windows run has uploaded a bundle. Reversible on Architect direction.
- **Product readiness marker not added.** The sketch allows a Dashboard DOM marker only if the helper exposes a product-side ambiguity. No such ambiguity is shown yet, so no `dashboard/*.js` change is planned and `scripts-dashboard-ui.md` stays unchanged. If the stress pass shows one, that is a sketch-permitted extension, and I would escalate before adding it.
- **The predicate might mask the very race it should expose.** "Any visible item" could pass where the old "first match" wait hung. That is the intended setup semantics: the repo mounted and is usable. If the first-item hypothesis is real, the remaining failure moves to whichever test asserts a specific item, and the bundle explains it there. The sketch forbids hiding a diagnosis, not making setup truthful.
- **pytest-playwright option names.** `--tracing`, `--screenshot` and `--output` are pytest-playwright's documented options. The coding loop confirms them against the installed version (`pytest --help`).
- **Charter gate.** `tests/**` has no charter mapping, so test-only edits should not require a charter. The workflow edit maps to Release Pipeline, which is updated in the same checkpoint.
- **Diagnostic cost on pass:** two listeners and one `report` attribute per test. Negligible against the 20-minute ceiling. Artifacts exist only on failure.

## Testing

- **Child-output tests** (new, in `test_harness.py`, using `dashboard_fleet_lifecycle_probe` / `dashboard_fleet`):
  - `server_diagnostics()` returns the live PID, `returncode is None`, and tails bounded to 200 lines and 16 KB;
  - the lifecycle probe's teardown assertions still pass with the tails attached.
- **Browser-state test:** `browser_diagnostics(page)` on a loaded Repo view reports `route-repo`, `repo-file-item` visible count ≥ 1, and no exception. On a closed page it returns an error string instead of raising.
- **Induced-failure test:** a test using `pytester` (or a subprocess pytest run on a tiny temp test module that loads this conftest) deliberately fails after navigation. It asserts that `gator-diagnostics.json` exists under the output dir with the expected keys, and that a passing twin writes nothing.
- **Readiness helper tests:**
  - `open_repo_when_ready()` succeeds for `alpha` and `beta`;
  - `repo="does-not-exist"` fails within the timeout with an `AssertionError` containing the diagnostic JSON. A short test timeout is used so the suite does not slow down.
- **Regression:**
  - full `tests/test_dashboard_ui/` on Windows locally;
  - a bounded repeated stress run of a mixed selection, for example 10 repetitions: `test_responsive_shell` route test, a file-tree test, a `test_loop_workspace` navigation test, and a `test_loop_liveness_ui` test;
  - CI on Ubuntu and Windows.
- **CI check:** the workflow linter (Release Pipeline tripwire) passes. A passing run uploads nothing; confirm the upload step is skipped.
- **Closing #70:** not part of this change. Monitor several normal Windows runs after it ships (sketch Validation 5).

## Charter Impact

- `.gator/charters/release-pipeline.md`, Workflow A: add a tripwire. The `dashboard-ui` job keeps Playwright trace and screenshot output only on failure and uploads it with `if: failure()`, naming the artifact by OS, Python, run attempt and SHA. Successful runs upload nothing. Reruns and timeout increases are not the flake response (#70).
- `scripts-dashboard-ui.md` and `scripts-dashboard.md`: no change. No product code is touched.
- No new charter. The test harness has no charter mapping in `INDEX.md`, and this plan does not create one.

## Coding Checkpoints

1. **Failure evidence capture** — the CI job keeps Playwright traces and screenshots on failure and uploads them with `if: failure()`. The harness keeps bounded post-ready child output and gains `server_diagnostics()` and `browser_diagnostics()`. A conftest hook writes `gator-diagnostics.json` only for failed browser tests. Includes the Release Pipeline charter tripwire. Verify: the new `test_harness.py` diagnostics tests, the induced-failure and passing-twin pytester test, the lifecycle probe, and the workflow linter.
2. **Shared repo readiness contract** — add `open_repo_when_ready()` with the repository-specific, any-visible predicate and the diagnostic timeout message. Verify: helper success for alpha and beta, and the failure-with-diagnostics test for an unknown repo.
3. **Migrate setup waits to the contract** — replace the repeated `goto(?repo=…)` + `.repo-file-item` setup pairs, including `_navigate_to_loop()`, with the helper. Leave the pre-fetch and `_treeState` assertions alone. Verify: full `tests/test_dashboard_ui/` on Windows and Ubuntu, plus the bounded mixed-selection Windows stress pass.
