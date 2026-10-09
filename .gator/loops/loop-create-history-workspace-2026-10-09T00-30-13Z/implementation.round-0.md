# Implementation: #56 Loop Create/History workspaces — Checkpoint 1 (Mode labels)

## Executive Summary

- **What changed:** each `/loops` item gains an additive boolean `mode_legacy`. A single mode projection (`loopModeInfo` / `modeBadge`) now puts a text mode badge (Coding / Planning / Planning · legacy / Unknown mode) on the live header, the outcome header and every sidebar card.
- **Key decision:** legacy is decided only from the recorded `mode` key (`mode_legacy` on list items, an absent raw `mode` on `/status`), never from feature names or artifacts. Mode is shown by text plus border style, never colour alone.
- **Main risk:** two new seeded terminal loops could disturb existing pins. The full loop UI subset (205 tests) passes unchanged.
- **Verified:** the checkpoint's Verify commands pass (1 server test, 5 Playwright tests), as do `tests/test_dashboard_loops.py` (114 passed, 6 skipped) and all `tests/test_dashboard_ui -k loop` tests.

## Implementation Summary

- **Server (`src/gator_command/scripts/gator-dashboard.py`, `/loops` list builder):** adds `"mode_legacy": "mode" not in session` beside the normalized `mode`. Nothing else in the list or `/status` projection changes. `/status` already exposes the raw `mode` through `_LOOP_STATUS_ALLOWED_KEYS`.
- **UI (`src/gator_command/scripts/dashboard/views/loop.js`):**
  - `loopModeInfo(src)` returns `{key, label}`:
    - `mode === "coding"` → Coding;
    - legacy (list `mode_legacy === true`, or a `/status` body whose `mode` is absent or null) → Planning · legacy;
    - `planning` / `planning-only` → Planning;
    - anything else (for example list `"unknown"`) → Unknown mode.
    
    A source with a boolean `mode_legacy` is treated as a list item. Otherwise the raw `mode` decides.
  - `modeBadge(info)` renders `<span class="loop-mode-badge" data-mode="…" aria-label="Loop mode: …">label</span>` through `escHtml`.
  - It is used in `renderLiveHeader` and `renderOutcomeHeader` (between the `h3` and the stage/outcome badge), and in `renderSidebarCard`, where `.loop-card-badges` wraps the mode badge and the existing `stageBadge`. The existing `.loop-badge` selectors are unaffected.
  - `headerFingerprint` adds `loopModeInfo(status).key`.
- **CSS (`dashboard.css`):** `.loop-mode-badge` is a neutral text colour with a per-mode border: coding 2px solid, planning 1px solid, legacy dashed with weight 500, unknown dotted italic. `.loop-card-badges` is an inline-flex wrapping group, and the card badge is compact.
- **Seed (`tests/test_dashboard_ui/test_loop_seed.py`):** adds `coding-finished` (mode `coding`, real-shaped `coding` block, no generations) and `planning-finished` (mode `planning-only`). Both are `ended_by_architect`, so neither becomes an approved-plan source in the coding create form. Existing seeded loops have no `mode`, so they are legacy.

## Charter Updates

- `.gator/charters/scripts-dashboard.md`: under the #43 M2a `/loops` bullet, adds a #56 note on `mode_legacy`: why it exists (normalization hides a missing mode), that it is computed from the session key only, and that `/status` is unchanged.
- `.gator/charters/scripts-dashboard-ui.md`, Loop workspace: a new **Mode projection (#56)** tripwire. It covers the single decision point, the four mappings and their inputs, no inference from names or artifacts, the markup and `aria-label`, the per-mode border styles (not colour alone), placement (live and outcome headers, sidebar cards in `.loop-card-badges`), and the `headerFingerprint` inclusion with the mutation-free pin.
- Checked against the code: the function names (`loopModeInfo`, `modeBadge`, `renderLiveHeader`, `renderOutcomeHeader`, `renderSidebarCard`, `headerFingerprint`) and the field name `mode_legacy` match the staged diff exactly.
- `.gator/commit_draft.md`: frontmatter filled in, plus a Checkpoint 1 entry in the change log.

## Verification

- `python -m pytest tests/test_dashboard_loops.py -k mode_legacy -q`: **1 passed**. `test_list_mode_legacy` covers four sessions (no mode, `planning-only`, `planning`, `coding`): `mode_legacy` is true only for no mode, and the normalized `mode` is unchanged.
- `python -m pytest tests/test_dashboard_ui/test_loop_workspace.py -k mode_badge -q`: **5 passed**:
  - `test_mode_badges_on_cards_and_headers` ×3: coding terminal, planning-only terminal and legacy active loop. Card and header give the same text, `aria-label` and `data-mode`, with exactly one stage/outcome `.loop-badge` still in the header.
  - `test_mode_badge_styles_differ_without_colour`: the computed border style and width differ across coding, planning and legacy.
  - `test_mode_badge_poll_is_mutation_free`: a MutationObserver on `#loop-region-header` sees zero mutations across more than two polls (excluding only the text-only `.loop-time-remaining` / `.loop-elapsed` patches), and the badge node stays connected.
- `python -m pytest tests/test_dashboard_loops.py -q`: **114 passed, 6 skipped**.
- `python -m pytest tests/test_dashboard_ui -q -k loop`: **205 passed**. This confirms the two new seeded loops do not disturb existing sidebar, coding, refresh, liveness, brief or markdown pins.
- **Known gaps:** the full `tests/test_dashboard_ui` and `tests` runs are deferred to final approval, as the approved plan specifies.
- **Staged-tree note:** the index already held `.gator/session-snippets/2026-10-09-gator-34a9d0e417d43.json` when this turn began (it was not added by this checkpoint). It is the per-commit evidence snippet that the next real commit includes by design, so it was left staged. The unstaged `.gator/.gator-version` and `.gator/runtime-pin.json` edits are pre-existing and not part of this candidate.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 3) — Mode labels |
| Checkpoint base tree | `7e01b49b16a02cb832fd21eda069d58736482b40` |
| Generation | 0 |
| Staged tree (candidate) | `b0e992c03ff4d4ca966405b433857c6bd8d20239` |
| Changed paths in this checkpoint | 10 (A 1, M 9) |
| Loop base HEAD | `34a9d0e417d431853181de99088547a9fce86698` |
| Loop base tree | `7e01b49b16a02cb832fd21eda069d58736482b40` |
| Current HEAD | `34a9d0e417d431853181de99088547a9fce86698` (dev) |
| Changed paths vs loop base (cumulative) | 10 |
| Unstaged / untracked residue | 3 other + 91 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 7e01b49b16a02cb832fd21eda069d58736482b40 b0e992c03ff4d4ca966405b433857c6bd8d20239
```

Cumulative context (approved checkpoints plus this one): `git diff 7e01b49b16a02cb832fd21eda069d58736482b40 b0e992c03ff4d4ca966405b433857c6bd8d20239`.

Changed paths in this checkpoint (status, path):

```text
M .gator/charters/scripts-dashboard-ui.md
M .gator/charters/scripts-dashboard.md
M .gator/commit_draft.md
A .gator/session-snippets/2026-10-09-gator-34a9d0e417d43.json
M src/gator_command/scripts/dashboard/dashboard.css
M src/gator_command/scripts/dashboard/views/loop.js
M src/gator_command/scripts/gator-dashboard.py
M tests/test_dashboard_loops.py
M tests/test_dashboard_ui/test_loop_seed.py
M tests/test_dashboard_ui/test_loop_workspace.py
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 91 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
