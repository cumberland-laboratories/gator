# Implementation Plan: #70 — Windows Dashboard UI flakes, Slice 1 (make failures attributable)

## Executive Summary

- This revision limits the plan to the sketch's Slice 1. The sketch says Slice 2 (the shared readiness helper) comes only after Slice 1's evidence confirms the failure class. Slice 2 and Slice 3 move to a later loop through an explicit evidence-review handoff.
- On failure only, the Windows `dashboard-ui` CI job keeps Playwright traces and screenshots and uploads them. A repository-owned `gator-diagnostics.json` records the failing phase, browser state, browser console and page errors, and bounded Dashboard child output. It uses a fixed, versioned schema.
- Key design choice: the bundle is assembled in `pytest_runtest_makereport`, while the `page` is still alive. It does not depend on fixture-teardown order. A setup failure before a page exists produces a server-only bundle.
- No product code, timeouts, reruns or server-concurrency changes. Verification uses focused harness and induced-failure tests, then one Dashboard UI suite run at final approval.

## Summary

The Windows-only `dashboard-ui` failures move among unrelated tests. The sketch makes attribution the first deliverable: the next failure must show whether the server exited, navigation landed on the wrong view, JavaScript failed, a request was delayed, or the problem was DOM visibility. This plan delivers exactly that.
- Failure-only Playwright artifacts and a CI upload.
- Bounded post-ready capture of the Dashboard child's output.
- A failure-only diagnostic bundle with a defined phase and fixture-lifecycle contract.

The readiness contract (Slice 2) and the cause fix (Slice 3) are deferred, each gated on that evidence.

## Response to Round 1 Findings

1. **Slice 2 before its evidence gate (High): accepted.** Slice 2 is removed from this plan, along with the former Changes 5–6 and Checkpoints 2–3. The handoff section below defines the gate: what evidence is required, who reviews it, and what the next loop's sketch must decide. The sequence is no longer changed by an implementer assumption.
2. **Incomplete migration inventory (High): resolved by deferral, with the inventory recorded as handoff input.** This plan migrates no call sites. Choosing the migration set is a Slice 2 design decision, so it belongs to the Slice 2 loop. The handoff records the sites the reviewer found as that loop's starting inventory:
   - `test_loop_workspace.py` lines 61, 323, 355, 1004, 1025, 1049, 1064, 1608, 2621, 3015 and 3091, in addition to those I listed;
   - the wrapper helpers in `test_responsive_shell.py`;
   - `test_html_preview.py` and `test_syntax_highlight.py`.

   The handoff also records the requirement for a semantic in-scope/out-of-scope rule.
3. **Fixture order and phase contract (Medium): addressed.** See Change 4. Capture happens in the `makereport` hookwrapper, before any teardown. Setup, call and teardown failures each have a defined outcome, including a server-only/no-page bundle. The induced-failure tests cover a call-phase failure and a setup-phase/no-page failure, and check that both bundles are bounded and safe to publish.
4. **Invalid dict composition (Medium): addressed.** The payload now has a stable schema (`gator-ui-diagnostics-v1`) with separate `browser`, `events` and `server` keys, pinned by a test. The readiness-timeout path itself is deferred with Slice 2. That loop reuses this schema rather than inventing one.
5. **Planning procedure not applied (Low): addressed.** `.gator/procedures/writing-implementation-plans.md` was read and is cited. The Approach states the planning path, module map, simplicity boundary and verification ladder. The checkpoint runs focused checks only; the broad Dashboard UI suite runs once, at final approval.

## Context Checked

- Architect brief: none listed by `gator loop status` (no `architect-brief.md` in the loop directory).
- `sketch.md`: scope, non-goals, constraints, Slice 1–3 sequence, validation plan, likely files.
- `findings.current.md` (round 1).
- `.gator/procedures/writing-implementation-plans.md`: planning path, module/simplicity rules, verification ladder.
- `.gator/charters/INDEX.md`: `.github/workflows/**` maps to Release Pipeline + Cross-Cutting. `tests/**` has no charter mapping.
- `.gator/charters/release-pipeline.md`, "Workflow A: Source CI": least-privilege, action-pin policy, workflow-linter rule, and the `dashboard-ui` 20-minute timeout tripwire.
- `.gator/charters/scripts-dashboard-ui.md`, `navigate() / showView() / setActiveRepo()` and `renderRepo()` entries: these define the view and selected-repo DOM the snapshot reads (`#view-slot` route class, the "▸ <name>" Repo label).
- `tests/test_dashboard_ui/_harness.py`: `build_dashboard_fleet()`, `read_ready_url()`, `spawn_reader_thread()`, `drain_queue()`, `terminate_and_wait()`.
- `tests/test_dashboard_ui/conftest.py`: fleet fixtures (session `dashboard_fleet`, function `dashboard_fleet_mutable`, session `dashboard_fleet_debug_off`), page fixtures, `dashboard_fleet_lifecycle_probe`.
- `.github/workflows/source-ci.yml`: the `dashboard-ui` job.
- Installed `pytest-playwright` 0.9.0 `pytest --help`: confirmed `--output` (default `test-results`), `--tracing {on,off,retain-on-failure}`, `--screenshot {on,off,only-on-failure}`.

## Approach

**Planning path: full planning loop.** Two things make this more than a direct change. It adds a new publish-safe artifact (a small schema shipped to CI artifacts), and it adds a fixture-lifecycle invariant: capture before teardown, without forcing browser fixtures on non-browser tests. The design has one clear direction, so a single checkpoint is enough.

**Module map: one responsibility.** "Failure evidence capture": when a Dashboard UI test fails, preserve enough bounded, safe evidence to classify the failure. It has three cooperating parts, and none is independently useful:

| Part | Purpose / invariant | Where |
|---|---|---|
| Child output tail | Post-ready Dashboard stdout/stderr stays available, bounded (200 lines, 16 KB per stream). The ready protocol is unchanged. | `_harness.py` |
| Snapshot functions | `server_diagnostics()` and `browser_diagnostics()` read state only. They never fetch, mutate or raise. | `_harness.py` |
| Failure hook and CI retention | The bundle is written only on failure, in the phase where the evidence still exists. CI uploads output only on failure. | `conftest.py`, `source-ci.yml` |

Splitting these into separate checkpoints would create test-only or CI-only pseudo-modules, which the procedure rejects.

**Key design decision: capture in `makereport`, not in fixture teardown.** pytest builds the call-phase report before any fixture teardown runs, so `page` and its context are still open there. That removes any dependency on finalizer order between our fixture and pytest-playwright's `page`/`context` fixtures. An autouse fixture only *attaches* event listeners; it never captures anything.

**Simplicity boundary.**
- Reuse pytest-playwright's built-in trace and screenshot retention; build no recorder of our own.
- No video (the sketch defers it until one trial).
- No new dependency.
- No product-side DOM marker.
- The snapshot's selector list is closed and fixed.
- **Rejected alternative:** writing the bundle from fixture teardown. It depends on finalizer ordering against pytest-playwright's `page`, and that ordering changes with fixture request order. That is the fragility Finding 3 identifies.

## Changes

### 1. Bounded post-ready child output
- File: `tests/test_dashboard_ui/_harness.py`
- What:
  - `spawn_reader_thread(stream, q, tail=None)`: when `tail` is given, each decoded line is also appended to it. `tail` is a `collections.deque(maxlen=200)`; `deque.append` is atomic under the GIL, so no lock is needed. Queue behavior is unchanged, so `read_ready_url()` and every ready-failure message are unchanged.
  - `build_dashboard_fleet()` creates `stdout_tail` and `stderr_tail`, passes them to the two reader threads, and adds `"server": {"proc": proc, "stdout_tail": stdout_tail, "stderr_tail": stderr_tail}` to the yielded dict. The `lifecycle_observer` keys and the teardown sequence are unchanged.
- Why: today the readers keep enqueueing after `Ready on`, but nothing reads the queues, so the post-ready server output that a failure needs is lost.

### 2. Read-only snapshot functions
- File: `tests/test_dashboard_ui/_harness.py`
- What:
  - `server_diagnostics(fleet)` returns `{"pid", "returncode", "stdout_tail", "stderr_tail"}`.
    - `returncode` is `proc.poll()`.
    - Each tail is a list of the last lines, trimmed to 200 lines and then to 16 KB total (oldest lines dropped first).
    - `fleet` may be `None` → returns `None`.
  - `browser_diagnostics(page)` returns `{"url", "title", "viewport", "dom"}`.
    - `dom` comes from one `page.evaluate` of a fixed script. It reads `document.readyState`, the `#view-slot` class list, the active `.sidebar-item` `data-view`, and the Repo label text.
    - It also reads `{count, visible}` for this closed selector list: `.repo-file-item`, `#view-slot .repo-file-item`, `.fleet-table`, `#loop-sidebar-nav`, `.loop-status-header`, `.docs-frame`, `.welcome`. Here `visible` counts elements whose `checkVisibility()` is true; this shows "matched but not visible" directly.
    - Every field is wrapped so that any exception (page closed, navigation in flight, evaluate timeout) records `{"error": "<type>: <message, ≤500 chars>"}` for that field. The function never raises.
- Why: classifies the failure (wrong view, missing root, hidden root, server dead) without a network request or any change to state.

### 3. Event listeners
- File: `tests/test_dashboard_ui/conftest.py`
- What: autouse function fixture `_ui_diagnostic_events(request)`.
  - When `"page"` is in `request.fixturenames`, it calls `request.getfixturevalue("page")`, attaches `page.on("console")` (all types) and `page.on("pageerror")` into one bounded list on `request.node` (last 100 entries, each `{"kind", "type", "text"}` with text ≤500 characters), then yields.
  - Otherwise it yields without touching `page`, so non-browser tests in this directory, such as the lifecycle probe, never start a browser.
  - It captures nothing.
- Why: console and page errors happen during the test, so the listeners must exist before the test body runs.

### 4. Failure-only bundle: phase contract
- File: `tests/test_dashboard_ui/conftest.py`
- What: `pytest_runtest_makereport` hookwrapper (`@pytest.hookimpl(wrapper=True)` or `hookwrapper=True` per the installed pytest). When the report for `setup`, `call` or `teardown` has `failed`, it writes `<output>/<slug>/gator-diagnostics.json`.
  - `<output>` is `item.config.getoption("--output")`.
  - `<slug>` is the nodeid with non-`[A-Za-z0-9._-]` characters replaced by `-`, truncated to 120 characters.
  - The fleet and page are looked up in `item.funcargs` only, never by creating fixtures. The fleet is whichever of `dashboard_fleet`, `dashboard_fleet_mutable` or `dashboard_fleet_debug_off` is present.
  - Phase behavior:

    | Failed phase | `browser` | `events` | `server` |
    |---|---|---|---|
    | `call` | `browser_diagnostics(page)` (page alive: no teardown yet) | bounded list | `server_diagnostics(fleet)` |
    | `setup`, page created | snapshot as above | bounded list (possibly empty) | if the fleet was created |
    | `setup`, before page or fleet (e.g. fleet startup raised) | `{"unavailable": "no page at setup failure"}` | `[]` | `null` or the snapshot; the fleet's own `RuntimeError` already carries the ready-protocol stdout/stderr in the pytest report |
    | `teardown` | `{"unavailable": "teardown phase"}` (the page may already be closed; not attempted) | bounded list | `server_diagnostics(fleet)` |

  - Schema (pinned by test):
    ```json
    {"schema": "gator-ui-diagnostics-v1", "nodeid": "...", "phase": "setup|call|teardown",
     "browser": {...} | {"unavailable": "..."}, "events": [...], "server": {...} | null}
    ```
  - A second failing phase for the same test writes `gator-diagnostics.<phase>.json` instead of overwriting.
  - Hook body errors are caught and written as `{"schema": ..., "diagnostics_error": "..."}`. The diagnostic path never masks or changes the test's own outcome.
- Publish safety: the bundle holds only the fields above. It never holds environment values (the fleet's `env` is never referenced), home or registry paths beyond what the child itself printed, or file contents. Each string and list is bounded by the limits in Changes 1–3, so the bundle has a known maximum size of about 60 KB.
- Why: sketch Slice 1, items 3–4, with the lifecycle contract from Finding 3.

### 5. CI failure retention and upload
- File: `.github/workflows/source-ci.yml` (`dashboard-ui` job only)
- What:
  - The run step becomes `python -m pytest tests/test_dashboard_ui/ -v --tb=short --tracing retain-on-failure --screenshot only-on-failure --output test-results/dashboard-ui`.
  - New step, `if: failure()`, using `actions/upload-artifact@v4`: `name: dashboard-ui-${{ matrix.os }}-py3.12-attempt${{ github.run_attempt }}-${{ github.sha }}`, `path: test-results/dashboard-ui/`, `if-no-files-found: ignore`, `retention-days: 14`.
  - Job permissions are unchanged; upload-artifact needs no additional scope.
  - The 20-minute timeout is unchanged.
- Why: sketch Slice 1, items 1–2. Passing runs upload nothing.

## Dependencies and Ordering

Change 1 comes before Change 2 (`server_diagnostics` reads the tails). Change 2 comes before Change 4. Change 3 comes before Change 4 (events). Change 5 is independent but is verified last. All five ship as one checkpoint.

## Slice 2 / Slice 3 Handoff (evidence gate)

- **Gate:** at least one failed Windows `dashboard-ui` run whose uploaded artifact holds a `gator-diagnostics.json` and a trace. A failure induced locally on Windows with this harness also counts, if the stress pass below reproduces one. The Architect reviews the bundle and classifies the failure into one row of the sketch's Slice 3 table.
- **The next loop's sketch must decide:**
  - the readiness predicate (informed by the observed class, e.g. whether the "resolved to 132 elements" failure was a hidden first match);
  - a semantic migration rule: direct repo-open setup is in scope; tests asserting pre-ready or transition state are out of scope;
  - the call-site inventory, starting from the reviewer's round-1 list (see Response 2) and the original list (`test_docs_view.py:100`, `test_loop_workspace.py` 61/387/1295/3032 and `_navigate_to_loop()`, `test_responsive_shell.py` 169/631/680/753/812, `test_welcome_ui.py:124`), with `test_responsive_shell.py:454` (pre-fetch) and `test_harness.py:222` (`_treeState`) as known exclusions;
  - whether a static no-new-ad-hoc-waits check is wanted;
  - the timeout payload, which reuses `gator-ui-diagnostics-v1`.
- This plan authorizes none of those.

## Assumptions, Risks, and Required Architect Decisions

- **Non-blocking:** `pytest-playwright` cleans its `--output` directory at session start. Diagnostics written under it are therefore per-run, which is the intended behavior. Locally, the default `test-results/` is already ignored or ephemeral; the coding loop confirms `.gitignore` coverage and adds `test-results/` there if missing.
- **Risk: `getfixturevalue("page")` in an autouse fixture changes fixture setup order** (page is created earlier within the test). That has no behavioral effect: `page` has no dependency on the fleet fixtures, and the tests navigate explicitly. The full-suite run at final approval verifies it.
- **Risk: listener overhead** is two callbacks per console message. Negligible.
- **Risk: a passing CI run never exercises the upload step.** It is verified once with a deliberately induced failure locally, not in CI. The workflow linter checks the syntax.
- **Charter gate:** test-only edits map to no charter. The workflow edit maps to Release Pipeline, which is updated in the same checkpoint.
- No blocking Architect decision is required for this plan. The Slice 2 gate is the Architect's review, by design.

## Testing

Each test proves one distinct risk:

| Test | Risk it proves |
|---|---|
| `test_server_diagnostics_tails_are_bounded_and_live` (`test_harness.py`, `dashboard_fleet_lifecycle_probe`): pid matches, `returncode is None`, tails ≤200 lines and ≤16 KB, ready protocol unaffected; the probe's own teardown asserts still pass | tail capture neither breaks the ready protocol or teardown, nor grows unbounded |
| `test_browser_diagnostics_reports_view_and_survives_closed_page`: on a loaded `?repo=alpha` page, `#view-slot` classes include `route-repo` and `#view-slot .repo-file-item` visible ≥1; after `page.close()` on a separate context page, returns error fields instead of raising | snapshot is truthful and never raises |
| `test_failure_bundle_phases` (`pytester`, parameterized over `call` and `setup-no-page`): the call case fails after navigation and asserts schema, `phase`, a `browser.dom` present, and `server.pid`; the setup case fails in a fixture before `page` and asserts `browser.unavailable`, `events == []`. Both assert size ≤64 KB and absence of the child env's sentinel variable value. A passing twin asserts no `gator-diagnostics*.json` | phase contract, publish safety, failure-only writing |

Checkpoint verification is these three tests plus the existing `test_harness.py`, with no full browser suite. Then the workflow linter on `source-ci.yml`.

**Final approval (run once):**
- full `tests/test_dashboard_ui/` locally on Windows;
- a bounded Windows stress pass (10 repetitions of a mixed selection: one `test_responsive_shell` route test, one file-tree test, one `test_loop_workspace` navigation test, one `test_loop_liveness_ui` test), run with the CI flags. Any failure it produces is retained as gate evidence;
- one local run with a temporarily induced failing test, to confirm that the trace, screenshot and `gator-diagnostics.json` land under `test-results/dashboard-ui/<slug>/`. The temporary test is not committed.

Ubuntu and Windows coverage then comes from CI.

## Charter Impact

- `.gator/charters/release-pipeline.md`, Workflow A: add a tripwire. The `dashboard-ui` job retains Playwright trace and screenshot output only on failure, along with the repository's `gator-diagnostics.json` (schema `gator-ui-diagnostics-v1`), and uploads them with `if: failure()`, naming the artifact by OS, Python, run attempt and SHA. Successful runs upload nothing. Reruns and timeout increases are not the flake response (#70).
- `scripts-dashboard-ui.md` and `scripts-dashboard.md`: no change. No product code is touched; the snapshot only reads DOM the charter already defines.
- No new charter. The test harness has no `INDEX.md` mapping.

## Coding Checkpoints

1. **Failure evidence capture** — bounded post-ready child output tails, the read-only `server_diagnostics()`/`browser_diagnostics()` snapshots, the autouse event listeners, the `makereport` failure-only `gator-diagnostics-v1` bundle with its setup/call/teardown phase contract, and CI failure-only trace/screenshot retention plus upload, with the Release Pipeline tripwire. Verify: the tail-bound, browser-snapshot and parameterized failure-bundle (`call`, `setup-no-page`, passing twin) tests, existing `test_harness.py`, and the workflow linter. At final approval: the full Dashboard UI suite on Windows, the bounded stress pass, and one induced-failure artifact check.
