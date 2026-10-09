---
date: 2026-10-08
type: implementation-sketch
issue: 56
feature: loop-create-history-workspace
recommended-path: direct-to-coding-with-focused-review
---

# #56 â€” Clear Loop Create, Active, and History Workspaces

## Goal

Make the Dashboard's Loop area understandable at a glance by separating three
different Architect activities:

1. **Create** a new planning or coding loop.
2. **Operate** the current active loop, including a clearly labelled recovery
   path when a participant needs to reconnect.
3. **Browse History** and inspect completed-loop evidence.

At the same time, make every loop's mode visible (Planning or Coding) and
rename the dashboard-wide commit timeline from ambiguous **History** to
**Commits**.

## Problem

The existing Loop workspace has useful partial structure, but it mixes creation,
active-loop control, recovery prompts, and historical cards closely enough that
an Architect can mistake a recovery action for normal loop operation.

In particular, the active-loop panel currently exposes **Copy Draftor prompt**
and **Copy Reviewer prompt** as unexplained buttons. Those prompts contain role
credentials and are appropriate for starting or reconnecting a participant
session—not for pasting into a participant that is already connected. The
current UI also makes it harder than necessary to scan prior loops and tell
whether each was planning or coding work.

## Intended Information Architecture

Under the primary Dashboard **Loop** navigation item, present two clear
loop-local views:

```text
Loop
  Create     start a loop; inspect/open an existing active loop when creation is unavailable
  History    browse terminal loops and their evidence
```

The current active loop is operationally important enough that it should be
reachable directly from **Create** (for example, an **Open active loop** call
to action), but it is not a historical artifact and must not be buried in the
History view.

The application-wide navigation item currently labelled **History** represents
commit history. Rename it **Commits**. Do not conflate it with Loop History.

## Proposed Behavior

### Create view

- Shows the loop creation form when no active loop blocks creation.
- If an active loop exists, shows a concise state-aware explanation and an
  obvious **Open active loop** action instead of a misleading disabled form.
- Keeps planning/coding creation choices and existing source-plan/revision
  behavior intact; this issue does not change loop state-machine semantics.
- Treats the post-creation handoff prompt cards as the normal place to copy
  participant entry prompts for newly started sessions.

### Active-loop workspace

- Opens from Create's active-loop call to action and remains the live control
  surface for the selected active loop.
- Replace the always-visible raw copy-prompt buttons with a clearly labelled
  **Participant recovery** section.
- Explain, in the section itself, that copied prompts are for a new/reconnected
  participant session and must not be pasted into a session that already joined.
- Show recovery controls only when useful: a role has not joined, has no
  reachable receiver, is stale/disconnected/released, or the Architect
  deliberately chooses to reconnect. For a healthy joined Goal-mode
  participant, de-emphasize or hide them.
- Keep the current security warning that a copied prompt carries a role
  credential.
- Preserve a recovery path even if a participant has disconnected; do not
  require returning to an external terminal or recreating the loop.

### History view

- Lists only terminal loops, newest first, in a dedicated browsing surface.
- Each history card and its selected detail prominently shows its mode:
  **Planning** or **Coding**. The label must not depend on a feature-name
  convention.
- Keeps direct access to the readable rendered/raw artifact viewer, timeline,
  decisions, and preserved evidence in the Loop workspace.
- Does not show active-loop recovery controls as though they apply to finished
  loops.

### Mode labels

Use one central, accessible mode projection based on the loop's authoritative
`mode` status field. Apply it consistently to:

- active-loop header;
- active-loop sidebar/card where space permits;
- historical cards; and
- selected historical-loop header/details.

Use a conservative legacy fallback (for example **Planning / legacy**) rather
than guessing based on filenames or feature text.

## Constraints

- Do not change role tokens, token issuance, loop stages, liveness semantics,
  or coding checkpoint behavior.
- #52 remains authoritative for accurately modelling participation, turn,
  receiver registration, and activity. This issue must not claim a joined role
  is absent solely because it has no optional watcher.
- #53's blocked/paused decision cards and #62's future Architect briefing must
  remain visible and usable in the active workspace.
- Keep artifact rendering in the established Loop workspace; do not make the
  user navigate to repository-file browsing merely to read historical evidence.
- Preserve keyboard navigation, focus restoration, responsive layout, and the
  existing incremental live-update/no-full-redraw behavior.

## Likely Implementation Seams

- `dashboard/views/loop.js`: loop-local view state, sidebar/sub-navigation,
  mode labelling, active/history filtering, recovery-control rendering and
  explanatory copy.
- `dashboard/dashboard.css`: compact sub-navigation, mode badges, recovery
  affordance, small-screen behavior.
- Dashboard shell/navigation template or frontend: rename the global commit
  history label to **Commits** without changing its route or data contract.
- Existing Dashboard UI tests: state transitions, history selection, mode
  labels, recovery visibility, and back/forward/direct-selection behavior.

Avoid a new backend endpoint unless the existing status/list projections cannot
distinguish terminal state, mode, and the receiver facts needed to render a
truthful recovery affordance. If a projection gap exists, add the smallest
allowlisted field rather than deriving sensitive liveness facts in JavaScript.

## Verification

1. **Create / active path**
   - No active loop: Create form is reachable and behaves as before.
   - Active planning and coding loop: Create clearly directs to that loop;
     active workspace remains directly reachable.
2. **Recovery clarity**
   - Healthy joined participants do not see unexplained copy controls.
   - A missing, released, stale, or disconnected participant exposes a
     labelled recovery action and credential warning.
   - Copying remains available after a real recovery need and does not mutate
     loop state.
3. **History**
   - Terminal planning and coding loops appear in History only; active loops do
     not.
   - Each card and selected detail shows the correct mode, including legacy
     fallback.
   - Rendered artifact navigation works from selected historical loops.
4. **Navigation and accessibility**
   - Loop Create, active inspection, and History support direct selection and
     browser back/forward without stale main content.
   - Global **Commits** navigation still reaches the existing commit history.
   - Keyboard focus and screen-reader labels identify the selected local view,
     mode badge, and recovery purpose.
5. **Regression**
   - Existing live polling and incremental patch tests remain green; a poll
     must not reset the selected history item, reading position, or open
     artifact panel.

## Non-Goals

- Fixing the underlying watcher/participation state model (#52).
- Adding observer roles, token accounting, or the Architect briefing.
- Reopening completed loops, changing history retention, or changing loop
  artifact formats.
- Making recovery prompts an automatic participant relaunch mechanism.

## Delivery Guidance

This is constrained Dashboard work and can go directly to coding from this
sketch, followed by focused browser/UI tests and a human UX review. Keep the
first pass to the existing Loop view/state machinery. Escalate to a planning
loop only if inspection shows the current API lacks the authoritative terminal,
mode, or receiver facts necessary to render recovery controls honestly.
