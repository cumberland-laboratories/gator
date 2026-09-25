---
message: "Dashboard loop workspace: sub-navigation, creation, handoff, and live/history refinement"
change-type: feature
significance: major
decision-tags: [dashboard, gator-loop]
agent: claude-opus-4-6
architect:
---

# Session Change Log

## loop.js — complete rewrite for secondary sidebar model

Reshaped the flat loop-list sidebar into a three-section secondary
sidebar: Create Loop action, Active (0-1 loop), History (terminal
loops newest-first). Added mode-driven main content rendering:

- **Creation workspace** (`renderCreateWorkspace`): feature name input,
  sketch source picker (browse endpoint dropdown + manual path toggle),
  advanced settings disclosure (max rounds, turn timeout), Create
  action calling existing start API with client-side validation and
  server error display including 409 race-recovery.

- **Participant handoff** (`renderHandoff`): post-creation prompt-copy
  cards for Draftor/Reviewer. Fetches from no-store prompt endpoint,
  copies to clipboard, nulls prompt variable immediately. Fallback
  textarea when clipboard API unavailable. Join state polling. "Open
  loop workspace" navigation is explicit — never auto-leaves on join.

- **Live vs history workspace** (`renderSelectedLoop`): live loops
  show status header, blocked-on-Architect card with pending decision
  link (`pendingDecision()` selects newest unresolved decision), prompt
  copy section, controls, timeline, artifacts. Terminal loops show
  outcome badge, completed date, no controls, no prompts.

- **Event-driven artifact enumeration** (`collectArtifactPaths`):
  derives immutable artifacts from event `artifact_path` fields and
  `status.decisions[]` instead of numeric round loop. Naturally
  includes round-zero artifacts. Deduplicates by path.

## gator-dashboard.py — sketch-sources endpoint + artifact pattern fix

- Added `_handle_sketch_sources()`: `GET /api/repo-by-key/<key>/sketch-sources`
  lists `.md` files from `.gator/artifacts/`, `.gator/threads/`,
  `.gator/active-threads/`. Reparse/symlink checks on candidate
  directories and entries. Uses `_resolve_repo_by_key()` containment.

- Tightened `_LOOP_ARTIFACT_PATTERNS`: `decision-request` pattern now
  matches `decision-request.decision-<N>.round-<R>.md` (was
  `[a-zA-Z0-9_-]+` which didn't match the dot in production filenames).

- Updated `_dispatch_loop_get()` to route both `/sketch-sources` and
  `/loops/...` under the `/api/repo-by-key/` prefix.

## dashboard.css — new styles

Added CSS for secondary sidebar sections, creation workspace, sketch
picker, handoff cards, prompt copy section, outcome header, and
blocked-card artifact link. Narrow-layout media query updated.

## Enforcer review corrections (revisions 6–8)

- **Handoff terminal auto-navigation removed**: `updateHandoffStatus()`
  no longer transitions to inspect mode on terminal stage. Stays on
  handoff, updates indicators only. Architect navigates explicitly.
- **Terminal handoff credential lockdown**: when terminal status is
  observed during handoff, copy buttons are disabled ("Loop ended"),
  fallback textareas removed, outcome badge shown, polling stopped.
- **Prompt-copy race guard (general)**: replaced handoff-only
  `handoffTerminal` flag with `_state.promptEpoch` counter incremented
  on terminal in both `updateHandoffStatus()` and `pollLoop()`.
  `copyPrompt()` captures the epoch before fetch and checks it after
  fetch and before every clipboard/fallback path. Covers both handoff
  and live inspection workspace.
- **Escape closes Advanced settings**: scoped `keydown` listener on
  the `<details>` element closes it on Escape without intercepting
  Escape elsewhere.

## Browser tests — 28 new tests (32 → 60)

Added focused coverage for the new workspace:
- B1–B4: sidebar sections, classification, empty states, create-disabled
- B5–B7: no-loops → create, history-only → create, active → inspect
- B8–B12: creation form, sketch dropdown + manual toggle, validation,
  successful creation → handoff transition, 409 race recovery
- B13–B17: handoff cards + guidance, copy calls prompt endpoint,
  draftor join keeps reviewer copy, open-workspace transition
- B18–B23: active controls+prompts, terminal read-only, blocked card
  with decision link, pending decision over resolved, round-zero
  artifact via timeline link
- Terminal handoff credential removal test
- In-flight handoff prompt copy race regression test (delayed response +
  terminal transition → no clipboard write, no fallback)
- In-flight live workspace prompt copy race regression test
- B14 clipboard verification (prompt text reaches clipboard)
- B15 post-navigation cleanup (no prompt in storage or DOM data-attrs)
- Escape closure of advanced settings disclosure test

Test seed extended with blocked loop (two decisions: resolved + pending)
and round-zero loop (plan.round-0.md fixture).

## pollLoop terminal-invalidation ordering fix

Moved `promptEpoch` increment in `pollLoop()` to immediately after
terminal status is identified, before awaiting `fetchEvents()`. Closes
the race window where an in-flight `copyPrompt()` could resolve during
the event-fetch wait and write to clipboard with the stale epoch.
Added `test_live_delayed_events_does_not_leak_prompt` regression test:
delays events response, releases prompt after terminal status but
before events resolve, verifies clipboard sentinel unchanged.

## Charters updated

- `scripts-dashboard-ui.md`: documented new render functions, mode
  state, secondary sidebar, creation workspace, handoff, token
  non-persistence, event-driven artifact enumeration, early
  `promptEpoch` invalidation in `pollLoop()`.
- `scripts-dashboard.md`: documented sketch-sources endpoint and
  tightened decision-artifact patterns.
