# Implementation: #70 Slice 1 — failure evidence capture (checkpoint cp1)

## Executive Summary

- When a Dashboard UI test fails, CI keeps a screenshot and a bounded (≤48 KiB) `gator-diagnostics.json` (`gator-ui-diagnostics-v1`) and uploads them only on failure. Passing runs upload nothing.
- **Deviation per Architect decision-1:** Playwright tracing is *not* enabled. `--tracing retain-on-failure` records every test. Measured at about +45% test time, it would push the Windows job past its 20-minute cap. The Architect ruled that CI must not get longer.
- The bundle is built in `pytest_runtest_makereport`, before teardown. It captures the phase, the view/DOM snapshot, the selected repository (via a new read-only `GatorShell.activeRepo()`), console and page errors, and the server output tails.
- Verified: 26 focused tests pass (1 skipped), actionlint is clean, an induced failure produces co-located artifacts, the full Dashboard UI suite passes, and pass-time is unchanged. The Architect asked for critique of whether this direction should continue; see "Open question".

## Implementation Summary

**Child output tails** (`tests/test_dashboard_ui/_harness.py`):
- `spawn_reader_thread(stream, q, tail=None)` also appends to a `deque(maxlen=TAIL_LINES)`.
- `build_dashboard_fleet()` creates `stdout_tail`/`stderr_tail` and adds `"server": {proc, stdout_tail, stderr_tail}` to the fleet dict.
- The ready protocol, queues, lifecycle observer and teardown are unchanged.

**Read-only snapshots** (`_harness.py`, new "#70: failure diagnostics" section):
- Constants: `BUNDLE_BYTES` 48 KiB, `TAIL_LINES` 200, `TAIL_BYTES` 8 KiB, `EVENT_LIMIT` 50, `EVENT_TEXT_BYTES` 300, plus URL, title, error and nodeid caps.
- `clip_bytes()` truncates by UTF-8 bytes.
- `bounded_tail()` keeps the last 200 lines and drops the oldest until the tail is ≤8 KiB.
- `server_diagnostics(fleet)` returns `{pid, returncode, stdout_tail, stderr_tail}`, or `None` with no fleet. It copies the deque defensively against concurrent appends.
- `browser_diagnostics(page)` returns `{url, title, viewport, dom}`. Each field is guarded and never raises. `dom` is one `page.evaluate` that reads:
  - `readyState`, the `#view-slot` classes, and the active sidebar `data-view`;
  - the Repo label;
  - `selected_repo` = `{name, key, source: "shell-state"|"unavailable"}`;
  - `history_entry` = `{kind: shell|repo-view|other|none, repo, repoKey}`, context only;
  - `{count, visible}` per selector, using `checkVisibility()`.
- `build_diagnostic_bundle()` keeps the last 50 events, clips them, and enforces the 48 KiB budget measured on compact `ensure_ascii=False` JSON. The final pass drops, in this fixed order:
  1. oldest events;
  2. oldest stdout lines;
  3. oldest stderr lines;
  4. otherwise `browser` is replaced by `{"unavailable": "size budget"}`.

  Counts are recorded in `truncated`.

**Fixtures and hook** (`tests/test_dashboard_ui/conftest.py`):
- Autouse `_ui_diagnostic_events`: only when `page` is in `fixturenames`, it attaches bounded `console`/`pageerror` listeners and stashes the page and events on the node. Non-browser tests never start a browser.
- `pytest_runtest_makereport` (`wrapper=True`): on any failed phase it writes the bundle. Fleet and page come from `item.funcargs` plus the stash; no fixture is created.
  - A teardown failure gives `browser: {"unavailable": "teardown phase"}`.
  - A failure with no page gives `{"unavailable": "no page at <phase> failure"}`.
  - A second failing phase writes `gator-diagnostics.<phase>.json`.
  - Diagnostics errors go to `gator-diagnostics.<phase>.error.json` and never alter the report.
- The folder is pytest-playwright's own per-test folder (slugified nodeid with the same long-name hashing), so the screenshot and the bundle sit together.

**Product accessor** (`src/gator_command/scripts/dashboard/dashboard.js`): `window.GatorShell.activeRepo()` returns a fresh `{name, key}` copy of `state.activeRepo`/`state.activeRepoKey`. No other change.

**CI** (`.github/workflows/source-ci.yml`, `dashboard-ui` only):
- The run step adds `--screenshot only-on-failure --output test-results/dashboard-ui`.
- A new `if: failure()` step uses `actions/upload-artifact@v6`, named `dashboard-ui-<os>-py3.12-attempt<n>-<sha>`, with `if-no-files-found: ignore` and 14-day retention. Permissions and `timeout-minutes: 20` are unchanged.

**`.gitignore`:** adds `test-results/`.

**Existing test touched:** `test_harness.py::test_builder_reaps_child_when_reader_thread_start_raises`. Its `flaky_spawn` stub now forwards `**kwargs` to the real spawner, because the builder passes `tail=`. The test's intent is unchanged.

### Deviations from the approved plan (all deliberate)

1. **No tracing (Architect decision-1).** The approved plan and sketch Slice 1 item 1 called for `--tracing retain-on-failure`. Measured on `test_responsive_shell.py` (22 tests, two runs each): 36/37 s without, 52/53 s with (+45%). Recent Windows job wall times are 13.6–15.9 min against a 20-minute cap. The Architect declined to lengthen CI. The Release Pipeline tripwire now records why tracing is absent.
2. **Selector list corrected.** The plan named `.fleet-table` and `.welcome`; neither exists in the Dashboard DOM. They are replaced with the real roots `#view-slot table.data-table` (Fleet, `views/fleet.js`) and `.welcome-workspace` (`views/welcome.js`).
3. **`actions/upload-artifact@v6`, not `@v4`.** This matches the repository's existing pins in `release-candidate.yml` and `promote-to-pypi.yml`.
4. **Bundle folder = pytest-playwright's slug,** not a bespoke regex slug, so the screenshot and bundle share one folder.
5. **The `repo.js`-entry test uses a repo search,** not a file click. Only search pushes `repo.js` history entries (`runCrossDocSearch`); tree clicks push nothing.
6. **New tests live in `test_failure_diagnostics.py`,** not `test_harness.py`, so the #70 pins sit together. The child pytest run is a subprocess with a temp root `conftest.py` (`pytest_plugins = ["test_dashboard_ui.conftest"]`), because the `pytester` plugin is not enabled in this repository.

### Open question (Architect decision-1)

The Architect asked whether this implementation should continue, or whether there is a better way to find the Windows UI failures. Facts relevant to that judgment:
- **Without tracing,** the bundle still separates the following failure classes: server exited (returncode plus stderr tail), wrong view or selection (`view_slot_classes`, `active_sidebar_view`, `selected_repo`), browser JavaScript error (`events`), and DOM visibility (per-selector `count`/`visible`). It cannot show request timing, so the "request delayed" class remains weakly evidenced.
- **A direct observation already made with this harness:** on a loaded `?repo=alpha` Repo view, `.repo-file-item` has `count: 131, visible: 1`. The tree is mostly collapsed. This bears on the "resolved to 132 elements, then waited for visibility" CI failure. Visibility of the first matching element is a live hypothesis, testable without CI.
- **Alternatives to weigh against shipping this in CI:**
  - a local Windows stress reproduction using the existing suite;
  - an on-demand (`workflow_dispatch`) Windows evidence job that can afford tracing without touching the per-push pipeline;
  - moving straight to the Slice 2 readiness contract, given the visibility evidence above.

  These are scope decisions for the Architect, not changes made here.

## Charter Updates

- `.gator/charters/release-pipeline.md`, Workflow A: a new tripwire for the failure-only screenshot plus `gator-diagnostics.json` (schema, 48 KiB, producer `tests/test_dashboard_ui/conftest.py`), the `if: failure()` upload with `actions/upload-artifact@v6` and its artifact name. It also says not to add `--tracing retain-on-failure`, with the +45% measurement and the Architect decision. Checked against the edited `source-ci.yml`.
- `.gator/charters/scripts-dashboard-ui.md`, the `navigate() / … / window.GatorShell` entry: the `window.GatorShell` bullet now lists `activeRepo()`. It is read-only, returns a fresh copy, and is used by `browser_diagnostics()`. A new tripwire says it is the only truthful key source in every history state, so diagnostics must not read the key from `history.state`. Checked against `dashboard.js` (`GatorShell`, the `popstate` fallback entry with `repoKey: null`, `setActiveRepo`).
- Test harness files have no `INDEX.md` mapping; no new charter.

## Verification

- `python -m pytest tests/test_dashboard_ui/test_harness.py tests/test_dashboard_ui/test_failure_diagnostics.py`: **26 passed, 1 skipped** (the existing Windows skip). This covers:
  - `test_server_diagnostics_tails_are_bounded_and_live`: lifecycle probe; the "Ready on" line appears in the tail; ≤200 lines and ≤8 KiB; probe teardown asserts pass.
  - `test_browser_diagnostics_reports_view_and_survives_closed_page`:
    - the shell state gives `{alpha, <repo_key from /api/data>, shell-state}`;
    - after a repo search, `history_entry.kind == "repo-view"` and the key is unchanged;
    - a closed page gives `dom.error` with no raise.
  - `test_bundle_budget_truncation`:
    - maximum-size bounded non-ASCII inputs fit with no final-pass truncation, keeping the newest entries;
    - the forced over-budget case drops events, then stdout, then stderr, in that order.
  - `test_failure_bundle_phases[call|setup-no-page]`, a child pytest run:
    - the call bundle has `dom.selected_repo`, `server.pid` and the induced console error;
    - the setup-before-page bundle has `browser.unavailable`, `events == []` and `server: null`;
    - both are ≤49,152 bytes and free of the env sentinel;
    - the passing twin writes nothing.
- **actionlint 1.x** (`actionlint-py`, scratch install) on `source-ci.yml`: clean.
- **Induced failure** with the CI flags (temp test, not committed): `test-failed-1.png` and `gator-diagnostics.json` in the same `out/<slug>/` folder (`trace.zip` also present in that run, which still used tracing).
- **Full suite:** `tests/test_dashboard_ui/` on Windows locally, **485 passed, 11 skipped** (run before the tracing removal; with tracing, 17 min 02 s).
- **Pass-time overhead after removing tracing** (`test_responsive_shell.py`, `--screenshot only-on-failure`): 43 s / 36 s with this change against 39 s / 40 s with the HEAD `conftest.py`. That is within noise, so no measurable cost.
- **Gaps:**
  - The bounded mixed-selection stress pass was not run. The Architect has asked to reconsider direction before more CI-oriented work.
  - The upload step is unexercised in CI; it was checked by actionlint only.
  - Ubuntu coverage comes from CI.
- **Index residue:** `.gator/session-snippets/2026-10-15-gator-c913f4701c75d.json` was already staged before this loop. It is the previous commit's governance snippet and is swept into the next commit by design. `.gator/commit_draft.md` is updated in the working tree and not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 1) — Failure evidence capture |
| Checkpoint base tree | `697bc20b5f2095e4ff0248be701e46cc61e32380` |
| Generation | 0 |
| Staged tree (candidate) | `7d1e25b5e99d6adf81ef9b509d94dfa612ffbd62` |
| Changed paths in this checkpoint | 10 (A 2, M 8) |
| Loop base HEAD | `c913f4701c75dc451ad7c892d261b2c9db79ee99` |
| Loop base tree | `697bc20b5f2095e4ff0248be701e46cc61e32380` |
| Current HEAD | `c913f4701c75dc451ad7c892d261b2c9db79ee99` (dev) |
| Changed paths vs loop base (cumulative) | 10 |
| Unstaged / untracked residue | 1 other + 17 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 697bc20b5f2095e4ff0248be701e46cc61e32380 7d1e25b5e99d6adf81ef9b509d94dfa612ffbd62
```

Cumulative context (approved checkpoints plus this one): `git diff 697bc20b5f2095e4ff0248be701e46cc61e32380 7d1e25b5e99d6adf81ef9b509d94dfa612ffbd62`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/release-pipeline.md
M .gator/charters/scripts-dashboard-ui.md
A .gator/session-snippets/2026-10-15-gator-c913f4701c75d.json
M .github/workflows/source-ci.yml
M .gitignore
M src/gator_command/scripts/dashboard/dashboard.js
M tests/test_dashboard_ui/_harness.py
M tests/test_dashboard_ui/conftest.py
A tests/test_dashboard_ui/test_failure_diagnostics.py
M tests/test_dashboard_ui/test_harness.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/commit_draft.md
```

Loop residue: 17 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
