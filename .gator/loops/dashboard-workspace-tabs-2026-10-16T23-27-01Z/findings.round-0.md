# Review: #80 Dashboard Workspace Tabs and Browser-Tab Identity

## Executive Summary

- **REVISE.** The plan has a coherent shell-owned routing design, a bounded session cache, and responsibility-based checkpoints.
- It credibly preserves the no-hidden-live-DOM and manual-activation constraints, and it identifies the snapshot packaging seam.
- However, it proposes substantial edits to `dashboard/dashboard.js` while omitting the Dashboard Server charter that `INDEX.md` explicitly routes to that file.
- The context gap matters because the new URL/history behavior must not accidentally disturb the Dashboard's server/snapshot boundary; the plan should read and record that charter before implementation.

## Verdict

REVISE

The plan needs one context and charter-impact correction before approval.

## Findings

### Finding 1: Required Dashboard Server charter is missing from Context Checked

**Severity**: Medium

**Location**: Context Checked; Charter Impact

**Issue**: `INDEX.md` routes `src/gator_command/scripts/dashboard/*.js` to both Dashboard Browser UI and Dashboard Server. The plan changes `dashboard.js` heavily—URL handling, history, snapshot-mode behavior, and a new browser-global shell seam—but cites only `scripts-dashboard-ui.md` and says no server charter impact. That makes the claimed context incomplete under the repository charter rules.

**Suggestion**: Read `.gator/charters/scripts-dashboard.md`, add the relevant server/snapshot and loopback-boundary constraints to Context Checked, and state explicitly whether the URL/query and snapshot changes require a Dashboard Server charter update or why they do not. Keep the implementation scope unchanged unless that reading reveals a real conflict.

## Scope Check

The plan stays within the sketch’s requested workspace contexts, URL/title identity, strip layout, and Fleet opening actions. Its five checkpoints are responsibility-based and build in a sensible order. The missing charter reading is a governance and boundary-comprehension gap, not a request for new functionality.

## What Looks Good

- `dashboard.js` remains the sole router; inactive contexts do not retain live polling or DOM.
- The versioned cache is bounded and deliberately excludes sensitive content.
- The explicit snapshot inlining and keyboard/selection rules are concrete and testable.
