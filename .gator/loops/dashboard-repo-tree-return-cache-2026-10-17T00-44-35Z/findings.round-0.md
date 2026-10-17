# Review: Dashboard Repository Tree — Instant Return from Workspace Contexts

## Executive Summary

- The plan scopes the work to browser-side Repo-view lifecycle/state handling and identifies the critical stale-response and listener-lifecycle hazards.

## Verdict

APPROVE

## Findings

No blocking findings.

## Scope Check

- The plan reads the cross-cutting, Dashboard Browser UI, and Dashboard Server charters required for `dashboard.js` and `views/repo.js`.
- It preserves the server’s name-addressed `/files` boundary and the #80 requirement that inactive contexts remain torn down.
- It includes a concrete cache boundary, mount-generation rule, and final Dashboard UI suite.

## What Looks Good

- Per-key state, selected-file ownership, and post-`await` guards are explicit rather than implicit.
- The cache is live-only, memory-only, bounded, and reconciled in the background.
- The proposed tests exercise stale arrivals, listener accumulation, cache eviction, cached render, reconciliation, and scroll restoration.

