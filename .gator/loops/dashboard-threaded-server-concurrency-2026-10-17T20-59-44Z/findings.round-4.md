# Review: Dashboard Threaded Request Server — Checkpoint 3

## Executive Summary

- REVISE: the gate correctly bounds draining and avoids self-deadlock for the initiating request.
- A repeat request for the *other* lifecycle action receives a success status even though no coordinator for that action is started.
- For example, restart followed by upgrade returns `{"status":"upgrading"}`, but only `restart_server()` runs; the reverse case is symmetric.
- Record the active lifecycle action and return an honest conflict/already-restarting response instead of claiming an action that will not occur.

## Verdict

REVISE

Checkpoint 3 must not report upgrade or restart success when a different, already-started lifecycle coordinator is the only one that will execute.

## Findings

### Finding 1: Cross-action repeats return a false success response

**Severity**: High

**Location**: `src/gator_command/scripts/gator-dashboard.py`, `DashboardHandler._start_lifecycle()` and the `/api/restart` / `/api/updates/upgrade` branches; `TestRestartDrain.test_repeat_restart_and_upgrade_start_one_coordinator`.

**Issue**: `_start_lifecycle()` returns `True` whenever `start_draining()` says a coordinator already exists, without retaining which coordinator owns the drain. Each route then sends its own success payload. Thus an upgrade request after restart reports `upgrading`, even though the test correctly proves that only the restart callback executes; restart after upgrade has the same fault. This is a false action acknowledgment and conflicts with the checkpoint’s stated honest-lifecycle guarantee.

**Suggestion**: Store the active lifecycle action with the drain state (or return it atomically from `start_draining`). A repeat of the same action may remain idempotently acknowledged if desired, but a different action must return a truthful non-success response (for example 409/503 naming the active action), without starting another coordinator. Replace the existing mixed repeat test expectation with assertions for both action orderings and the response contract.

## Scope Check

The candidate stays within the approved restart/upgrade-drain checkpoint. This finding corrects the response contract for the two explicitly scoped lifecycle routes and does not expand the feature.

## What Looks Good

- Normal in-flight POST draining, bounded timeout behavior, and coordinator-start failure recovery are well covered.
- The gate remains outside route-specific locks and leaves GET availability unchanged during the drain.

## Reviewed Candidate

<!-- Captured by the gator loop CLI at review submission. -->

| Fact | Value |
|---|---|
| Verdict | REVISE |
| Reviewed staged tree | `87b50895006f835b8cba32c8ca35e8e9ed733fdd` |
| Reviewed HEAD | `9368471a7e718c6ba794a121a349b21bd029c0d3` |
| Candidate round | 2 |
| Checkpoint | cp3 (3 of 4) — Restart and upgrade drain |
| Checkpoint base tree | `42ed56931b0b7c4f9d7bb21521c4b66813985b6c` |
| Generation | 4 |
| Live candidate unchanged at review | yes |
