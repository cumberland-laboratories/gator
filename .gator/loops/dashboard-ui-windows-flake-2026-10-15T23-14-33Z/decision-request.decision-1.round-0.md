# Decision Request: Playwright tracing cost vs the 20-minute `dashboard-ui` job cap

## Decision Needed

The approved plan (and sketch Slice 1, item 1) retains a Playwright trace on failure via `--tracing retain-on-failure`. Measured cost: that mode records every test and discards passing traces, which adds about 45% to test time. Combined with current Windows job durations, this would likely exceed the job's 20-minute `timeout-minutes`. Which way should Slice 1 go?

## Context

- **Measured locally (Windows, this machine).** `tests/test_dashboard_ui/test_responsive_shell.py`, 22 tests, two runs each way:
  - without flags: 36 s / 37 s;
  - with `--tracing retain-on-failure --screenshot only-on-failure`: 52 s / 53 s (about +45%).

  Screenshot `only-on-failure` costs nothing on a pass, so the overhead is the tracing.
- **Full suite locally with the CI flags:** 485 passed, 11 skipped, 17 min 02 s.
- **Recent Windows `dashboard-ui` CI job wall times** (setup included), from `gh run`:
  - 15 min 54 s (2026-10-15);
  - 14 min 59 s and 14 min 09 s (2026-10-13);
  - 13 min 36 s (2026-10-12).

  Setup is about 4 minutes (Release Pipeline tripwire), so the test step is about 10–12 minutes. +45% makes that about 14.5–17.5 minutes, giving a job time of about 18.5–21.5 minutes against the 20-minute cap.
- **Release Pipeline tripwire:** "Revisit the cap when the UI suite grows; a cancelled run is not a pass."
- **Sketch non-goals:** no blanket *per-test* timeout increases, no reruns. The job-level cap is not named.
- **Separate timing concern:** tracing also slows every test. That shifts timing on exactly the Windows race being diagnosed; it could make the flake more or less frequent.
- **Everything else in checkpoint 1 is implemented and verified:**
  - 26 focused tests pass (1 skipped);
  - actionlint passes;
  - an induced failure produced the trace, screenshot and `gator-diagnostics.json` in one folder;
  - the full suite passes.

  Nothing is staged yet.

## Options Considered

1. **Keep tracing; raise the `dashboard-ui` job cap from 20 to 30 minutes.** Update the Release Pipeline tripwire with the new measurement.
   - Delivers the sketch's Slice 1 as written: the trace has network timing, which is the best evidence for the "request delayed" class.
   - Cost: about 5 minutes more on every Windows and Ubuntu run, and the tracing timing shift.
2. **Drop tracing for now; keep `--screenshot only-on-failure` and `gator-diagnostics.json`.**
   - Zero pass-time cost and no timing shift.
   - The bundle still classifies server exit, wrong view, JavaScript errors and DOM visibility. It loses network timing, so the "request delayed" class becomes weaker evidence.
   - Departs from the sketch's Slice 1, item 1.
3. **Custom lightweight tracing.** Start our own context tracing with `snapshots=False, screenshots=False` (network, console and actions only), and save it only on failure.
   - More harness code beyond the approved plan. Its overhead is unmeasured; likely smaller, but not zero.

## Recommendation

Option 1 if you want the sketch's Slice 1 exactly and accept slower CI. The cap is a hang guard, not a per-test timeout, and the tripwire anticipates revisiting it.

If you weigh "don't perturb the race" more highly, Option 2 is the cleaner first step. Tracing can be turned on later in a targeted evidence run. I lean slightly towards Option 2, because tracing changes the timing of the very race it is meant to observe. This is genuinely your call.

## Consequence of Delay

The coding loop stays blocked. The implementation is complete in the working tree, nothing is staged, and I will apply your choice and submit right after the unblock.
