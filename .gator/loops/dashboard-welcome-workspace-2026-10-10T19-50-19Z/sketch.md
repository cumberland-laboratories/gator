---
date: 2026-10-10
type: implementation-sketch
issue: 72
feature: dashboard-welcome-workspace
recommended-path: direct-to-coding-with-focused-review
---

# #72 — Dashboard Welcome Workspace and Session-Opening Prompt

## Goal

Turn the Dashboard's Gator head/logo into a useful, vendor-neutral Welcome
workspace. It should help a new Architect understand Gator, gatorize a
repository, and deliberately start a governed session without relying on a
Gator-managed `AGENTS.md` or other native agent file.

The welcome workspace is top-level Dashboard content. Its navigation is a
horizontal tab bar across the top of the **main content pane**. It reuses the
interaction language of Loop's Create / History tabs—text labels, selected
weight, and an underline—but is not a second sidebar and must not be confined
to a narrow sidebar card.

As part of the same visual-system refinement, move Loop's existing **Create /
History** selector from its sidebar into an equivalent full-width tab bar at
the top of Loop's main pane. Welcome and Loop then use the same top-level
content-navigation treatment. This is a presentation and view-composition
change only; Loop's existing state machine, APIs, live polling, and evidence
rendering remain intact.

## Product Rationale

Gator 2.24.0 intentionally treats `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md`
as repository-owned files. That avoids vendor-file conflicts, but it also means
an Architect needs a clear, visible place to discover the deliberate session
handshake. The Welcome workspace provides that place.

`gator init` remains the canonical source of the resolved `GATOR_INIT.md`
path and the required reading order. The Dashboard must teach the behavior,
not duplicate a layout-dependent path or a copy of the session protocol.

## Intended Information Architecture

Clicking the Gator logo opens the Welcome workspace. Its main-pane tab bar has
four topics, in the order a new Architect normally needs them:

```text
Welcome
────────────────────────────────────────────────────────────────────
What is Gator? | What Gator can do | Gatorize a repo | Start a session with Gator
═══════════════

[selected topic content]
```

The selected tab has a strong text treatment and a visible underline. The bar
extends across the Welcome content width, with a subtle full-width baseline
below it. Loop adopts the same main-pane bar, so the two workspaces share an
obvious navigation grammar. The selector no longer needs to occupy the narrow
Loop sidebar.

### Layout reference — shared sidebar, full-width main-pane tabs

The Dashboard's left sidebar stays persistent. Fleet, Commits, Loop, Docs, and
Updates remain sidebar navigation. The visual change is only inside the right
main pane after **Loop** or the logo-driven **Welcome** view has been selected.

```text
Loop selected
┌──────────────┬──────────────────────────────────────────────────────────┐
│ LOGO         │ Loop   <selected repository>                              │
│              │──────────────────────────────────────────────────────────│
│ Fleet        │ Create   History                                          │
│ Commits      │══════════════════════════════════════════════════════════│
│ Loop       → │                                                          │
│ Docs         │ <Loop content>                                           │
│ Updates      │                                                          │
└──────────────┴──────────────────────────────────────────────────────────┘

Logo / Welcome selected
┌──────────────┬──────────────────────────────────────────────────────────┐
│ LOGO       → │ Welcome to Gator!                                        │
│              │──────────────────────────────────────────────────────────│
│ Fleet        │ What is Gator? | What Gator can do | Gatorize a repo |   │
│ Commits      │ Start a session with Gator                               │
│ Loop         │══════════════════════════════════════════════════════════│
│ Docs         │                                                          │
│ Updates      │ <Welcome topic content>                                  │
└──────────────┴──────────────────────────────────────────────────────────┘
```

In both cases, the tab labels are left-aligned beneath the view header, but
the horizontal baseline reaches the **right edge of the main pane**. It does
not stop after the final tab label and it does not live inside the sidebar.
The selected label has its own underline above that shared baseline. Loop's
current narrow sidebar-tab treatment is the surface being replaced.

The first tab is the default. Reopening Welcome during the same view instance
may preserve the selected topic, but a fresh Dashboard load should land on
**What is Gator?**. No query parameter, browser-history payload, local storage,
or dashboard API needs to contain copied prompt text.

### Consistent Loop main-pane navigation

Loop keeps its two existing local views and their current meanings:

```text
Loop
────────────────────────────────────────────────────────────────────
Create | History
════════

[creation workspace, active-loop explanation, or selected-loop inspection]
```

- **Create** continues to show the creation form when no loop is active, or the
  existing active-loop explanation and **Open active loop** action when one is
  active.
- **History** continues to filter the sidebar list to terminal loops. Selecting
  a card still opens its existing read-only inspection workspace in the main
  pane.
- The sidebar becomes a supporting list surface—Create's action/active-loop
  list or History's terminal-loop list—rather than the owner of the tab
  control.
- The current Loop sub-state remains authoritative. Switching the main-pane
  tab must preserve the same `create | history` selection, active/terminal
  selection behavior, browser-history restoration, and incremental polling
  guarantees already exercised by Loop tests.

This keeps a useful Loop distinction: the tab chooses the list/context, while
the main pane can still inspect a selected active or historical loop. It does
not require turning History into a separate page or discarding a selected
loop merely because the Architect changes tabs.

## Content Model

The workspace should reuse and link to existing Gator documentation instead of
creating a competing body of governance prose.

### What is Gator?

- A short explanation: Gator is the Git-native governance layer for
  AI-assisted engineering, not an AI coding framework or hosted audit tool.
- A concise statement of the charter-first model and Git-native evidence.
- A clear next action toward **What Gator can do** or **Gatorize a repo**.
- Source material: `README.md`, `.gator/mission.md`, and
  `docs/architecture.md`.

### What Gator can do

- Organize the existing capabilities into a small, scannable set: governed
  session opening, charters and commit evidence, local Dashboard inspection,
  and governed Loop collaboration.
- Describe benefits in Architect language, not as a full command reference.
- Link interested readers to the relevant documentation rather than embedding
  long procedural content.
- Source material: `README.md`, `docs/how-to-use-gator.md`, and
  `docs/architecture.md`.

### Gatorize a repo

- Explain that gatorizing adds Gator's `.gator/` layer, templates, hooks, and
  Dashboard registration while preserving repository-owned native agent files.
- Present the canonical command, `gator gatorize <target-directory>`, as a
  copyable command or clearly distinguished code sample if the current shell
  already has a standard command-copy pattern.
- State the expected next step: open the repository in the preferred coding
  agent, then start the session handshake.
- Source material: `README.md` and `docs/how-to-use-gator.md`.

### Start a session with Gator

This is the outcome-oriented tab. It explains, in plain language, what the
Architect should expect:

1. Paste the prompt into the coding-agent session for the repository.
2. The agent runs `gator init`.
3. The agent reads the Gator-owned entry document and required context before
   substantive work.
4. The Architect can then give the task with a shared governance context.

It includes one obvious **Copy session-opening prompt** control. The exact
copied text is deliberately vendor-neutral and layout-neutral:

```text
Run gator init in this repository. Treat its output, including the required
session-opening reads, as binding. Do not provide a substantive response until
those reads are complete.
```

After a successful copy, the control gives an accessible, visible confirmation
(for example, **Copied** plus a polite live announcement). If the Clipboard API
is unavailable, use the Dashboard's established copy fallback pattern; do not
silently fail. The prompt is transient: it must not be logged, persisted, or
put into navigation state.

## Interaction and Accessibility Contract

- Make the logo a real button or link with an accessible name such as
  **Open Welcome**; it must be keyboard reachable and not merely a decorative
  image click target.
- Use a semantic `role="tablist"`, `role="tab"`, and `role="tabpanel"`
  relationship for the four Welcome topics. Use roving `tabindex`,
  `aria-selected`, and Left/Right/Home/End keyboard navigation, matching the
  established Loop tab behavior.
- The selected topic is conveyed by text weight and underline, never colour
  alone. Focus has a visible focus indicator.
- The tab bar remains usable at narrow widths: wrap only if necessary; do not
  make the labels unreadably small or clip the final session tab.
- A tab switch replaces only Welcome's topic panel. It must not reload fleet
  data, alter repository selection, or disturb the Dashboard's global shell
  state.
- The Welcome workspace is useful without a selected repository. It must not
  enable Repo, Docs, or Loop navigation or imply that a repository is active.

## Likely Implementation Seams

- `dashboard.html`: make the brand/logo an intentional Welcome navigation
  control and load a small `views/welcome.js` module before the shell.
- `dashboard.js`: add the `welcome` view to `VIEW_META`, register logo routing,
  and retain the existing shell-owned Back/Forward behavior. Welcome has no
  sensitive sub-state; a minimal topic sub-state is optional only if the shell
  can own it consistently.
- `dashboard/views/welcome.js` (new): own fixed topic content, the accessible
  full-width tab bar, copy behavior, and its small local state. It should make
  no new backend request unless implementation inspection identifies a genuine
  need.
- `dashboard/views/loop.js`: relocate the already-owned Create / History
  tablist to the stable main Loop workspace shell. Keep its existing `_state`
  view selection, `applyTabState()` semantics, keyboard behavior, shell
  sub-state, selection rules, and poll-safe DOM patching; only its composition
  and container change.
- `dashboard.css`: extract a visually compatible shared main-pane tab
  treatment for Welcome and Loop. A full-width container owns the baseline and
  spacing; Loop's sidebar retains only list/action styling.
- Dashboard UI tests: verify Welcome routing, default topic, keyboard tabs,
  selected-state styling, copy success/fallback, responsive layout, and no
  repository-context mutation. Extend the existing Loop workspace tests to
  pin the relocated tab bar, active/history list behavior, selected-loop
  persistence, polling stability, and Back/Forward restoration.

## Constraints

- Do not create, edit, repair, refresh, or recommend changing `AGENTS.md`,
  `CLAUDE.md`, `GEMINI.md`, or other repository-owned agent files.
- Do not hard-code `.gator/.includes/GATOR_INIT.md` into the copied prompt.
  `gator init` resolves and reports the canonical path for the repository.
- Do not reproduce the full constitution, loop protocol, or documentation in
  the Welcome pane. Keep the content concise and link outward where useful.
- Do not make Welcome depend on a registered repository or on an active Loop.
- Do not introduce a framework, remote dependency, or telemetry.

## Verification

1. Clicking the Gator logo opens Welcome from Fleet, a repository view, and
   with no repository selected.
2. A fresh load selects **What is Gator?**; mouse and keyboard navigation
   select all four tabs with correct ARIA state and focus behavior.
3. The tab row spans the main Welcome pane and retains a full-width baseline;
   it is visibly distinct from Loop's sidebar-local tab strip while using the
   same selected-state language.
4. The Start-a-session panel explains the Architect flow, copies exactly the
   approved vendor-neutral prompt, confirms success accessibly, and has an
   honest Clipboard-unavailable fallback.
5. No welcome interaction changes repository context, enables a dimmed
   repository-scoped tab, posts to an endpoint, or creates native agent files.
6. Browser Back/Forward remains shell-owned and never exposes copied prompt
   text in history state.
7. Existing Fleet, Loop, Docs, and Commits navigation remains unchanged.
8. Loop's Create / History tabs appear across the top of its main pane with
   the same accessible selected-state grammar as Welcome. Switching either
   tab changes the sidebar list/context without losing a selected loop,
   resetting a half-filled creation form, or rebuilding stable live regions on
   an unchanged poll.

## Non-Goals

- A guided installer, automatic gatorization, or dashboard-driven execution of
  `gator gatorize`.
- Per-vendor onboarding flows or vendor-specific prompt variants.
- Reinstating managed native agent instruction files.
- A replacement for the detailed README, architecture guide, or Gator docs.
- Persisting Welcome completion, analytics, or user onboarding progress.

## Delivery Guidance

This is a bounded client-side Dashboard feature and can proceed directly to
coding with focused UI review. Inspect the shell's current history contract
before deciding whether the selected Welcome tab needs Back/Forward state; the
smallest safe first implementation may keep it view-local and reset it on a
fresh mount. Keep the copy-control behavior aligned with any existing
Dashboard copy utility so success and fallback semantics do not diverge.
