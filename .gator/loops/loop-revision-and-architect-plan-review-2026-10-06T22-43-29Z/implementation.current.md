# Implementation: #51 — Checkpoint 3 (Dashboard creation and inspection of plan sources)

## Executive Summary

- **Changes:**
  - **Server:** the Dashboard start route accepts `plan_path` / `revise_from`, with type and conflict checks only. `init_loop` stays the single validator and receives lexical paths. `/status` gains strict, positionally bound provenance views; three fixed artifact names are served; `/prompt` and `/loops` carry provenance pointers.
  - **UI:** a "Plan source" choice in the create form, a source line, provenance-first artifact labels, the timeline label, and the coding-loop feature prefill.
- **Key decision:** no new routes and no content validation in the server. Provenance reaches the browser only through `fixed_artifact_view` / `verify_fixed_artifact` against fixed names, never through the generic status allowlist.
- **Main risk:** UI regressions in the create form. Pinned by focused Playwright tests, and by the broad suite run once at final approval per the procedure.
- **Verified:** focused results are 10 API tests and 5 UI tests passing. The broad final-approval suite: **1603 passed, 20 skipped, 0 failed**.

## Implementation Summary

**`src/gator_command/scripts/gator-dashboard.py`**
- **`_handle_loop_start`:**
  - `plan_path` / `revise_from` must be non-empty strings;
  - both together, either with `mode: coding`, or `revise_from` without `sketch_path` gives 400; `sketch_path` is optional with `plan_path`;
  - `_lexical()` makes repo-relative inputs absolute without `resolve()`, so `read_governed_input` still sees links and aliases. A revision start's sketch also goes through the host's governed reader; an ordinary or optional sketch keeps the existing server check;
  - everything is passed to `init_loop(plan_path=…, revise_from=…)`, and its `ValueError` / `FileNotFoundError` returns 400 (atomic).
- **`_handle_loop_status`** (planning sessions only) adds `planning_source`, plus `plan_source: {view, check, sketch_present}` or `revision: {source_loop_id, baseline: {view, check}, approval: {view, check}}`. These are built from the session helpers with FIXED names, and are never in `_LOOP_STATUS_ALLOWED_KEYS`.
- **`_LOOP_ARTIFACT_ALLOWLIST`** gains `architect-plan.md`, `revision-baseline-plan.md` and `revision-baseline-approval.md`.
- **`/prompt`** adds one provenance pointer line (no content).
- **`/loops`** planning items gain `planning_source`.

**`src/gator_command/scripts/dashboard/views/loop.js`**
- **Create form:**
  - a "Plan source" radio group (sketch / revision / architect_plan) with `#loop-revise-select` and `#loop-plan-path` fields; the sketch label changes to "Revision sketch" or "Sketch source (optional)";
  - submit sends exactly the chosen source's fields;
  - Create is disabled for a revision with no approved sources.
- **Coding create:** `prefillFeature` fills the feature name from the selected approved source only when the field is empty or still holds our own earlier prefill, and it stays editable.
- **Inspection:**
  - `#loop-region-source` (`renderSourceLine`, `sourceFingerprint`) gives a plain-words source line with `[!! …]` integrity text;
  - `renderArtifacts` lists provenance first (`sourceArtifactEntries`) with labels; a revision loop's `sketch.md` is "Revision sketch"; an Architect-plan loop without a sketch lists no `sketch.md`;
  - `artifactsFingerprint` includes the provenance views;
  - `EVENT_LABELS.architect_plan_submitted` is "Architect plan — awaiting Reviewer".

**`dashboard.css`:** plan-source fieldset and `.loop-source-line` styles.

## Charter Updates

- `.gator/charters/scripts-dashboard.md`: a new "#51 planning sources" bullet covering start fields, the lexical-path rule, strict status views, the allowlist names, `/prompt` pointers and `/loops` items, pinned by `TestPlanSources51`.
- `.gator/charters/scripts-dashboard-ui.md`: a new "Planning sources (#51)" bullet covering create-form modes and the prefill, the source line, artifact order and labels, the timeline label, and mutation-free polls.
- `.gator/charters/scripts-cross-cutting.md`: the checkpoint-3 additive HTTP and JSON fields.

## Verification

- `python -m pytest tests/test_dashboard_loops.py -k PlanSources51`: **10 passed**.
  - An Architect-plan start returns 201: Reviewer stage, `planning_source`, `plan_source.check == ok`, `sketch_present` false, a view with exactly three keys, `architect-plan.md` served byte-for-byte, the `/prompt` pointer and `/loops` `planning_source`.
  - A revision start against an approved loop: the views are ok, both baselines are served, and the `/prompt` pointer appears.
  - Seven rejection cases are each pinned to their error text, with no loop directory created: non-string `plan_path`, empty `revise_from`, both, coding conflict, missing sketch, outside the repo, and a plan that fails the draft check.
  - Lookalike artifact names are refused; an ordinary loop reports `sketch` and no provenance keys.
- `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py -k "posts_only or prefill or inspection"`: **5 passed**. These pin the exact POST bodies for the architect_plan and revision modes, the editable coding prefill, the Architect-plan source line, artifact order and label, the omitted sketch, the timeline label and **0 mutations** over two polls, and the revision labels including the `[!! DIGEST MISMATCH]` text.
- **Final-approval broad suite** (once, per the verification ladder): `python -m pytest tests/test_loop*.py tests/test_dashboard_loop*.py tests/test_dashboard_loops.py tests/test_dashboard_ui/ tests/test_snapshot.py tests/test_packaging.py -o faulthandler_timeout=180`: **1603 passed, 20 skipped, 0 failed** (17:58). This includes the `loop.js` snapshot inlining test, all earlier #51 checkpoint tests and the protocol drift guards.
- **Residue:** this loop's directory and the earlier session snippet are untracked and not staged.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp3 (3 of 3) — Dashboard creation and inspection of plan sources |
| Checkpoint base tree | `ba55f3a814dc411f181fc291290ffab2a7391bfc` |
| Generation | 2 |
| Staged tree (candidate) | `95f930284d5e0692fd97220a6b4d6a5cbbb0843d` |
| Changed paths in this checkpoint | 9 (M 9) |
| Loop base HEAD | `2d6996c33c4b84c29cf172ec38f591a674ce2933` |
| Loop base tree | `137f6ef8607c6905187f2f1f8968bf8052aed995` |
| Current HEAD | `2d6996c33c4b84c29cf172ec38f591a674ce2933` (dev) |
| Changed paths vs loop base (cumulative) | 17 |
| Unstaged / untracked residue | 1 other + 9 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff ba55f3a814dc411f181fc291290ffab2a7391bfc 95f930284d5e0692fd97220a6b4d6a5cbbb0843d
```

Cumulative context (approved checkpoints plus this one): `git diff 137f6ef8607c6905187f2f1f8968bf8052aed995 95f930284d5e0692fd97220a6b4d6a5cbbb0843d`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-cross-cutting.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-dashboard-ui.md
M .gator/charters/scripts-dashboard.md
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/dashboard/dashboard.css
M src/gator_command/scripts/dashboard/views/loop.js
M src/gator_command/scripts/gator-dashboard.py
M tests/test_dashboard_loops.py
M tests/test_dashboard_ui/test_loop_workspace.py
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 9 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
