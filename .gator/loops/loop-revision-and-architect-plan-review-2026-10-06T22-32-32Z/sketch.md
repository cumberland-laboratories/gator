---
date: 2026-10-06
type: implementation-sketch
issue: 51
feature: loop-revision-and-architect-plan-review
recommended-path: planning-loop-review
supersedes: 2026-10-04-loop-revision-planning-and-architect-plan-source-sketch.md
---

# #51 — Revision Planning and Reviewer-Gated Architect Plans

## Goal

Keep one meaning for an **approved implementation plan**: it is a plan in a
planning loop that the Reviewer has approved. Add two explicit ways to start a
new planning loop from Architect-provided material without creating a weaker
direct-to-coding path:

1. **New revision planning loop** — begin a separate planning loop from an
   approved plan plus a revision sketch.
2. **Architect-originated draft plan** — the Architect supplies a complete
   plan as the initial plan artifact; Gator starts at Reviewer `plan_review`,
   skipping only the initial Draftor authoring turn.

Both paths end in an ordinary reviewer-approved planning loop. Only then may
the Architect create a coding loop. This includes compact plans for small
changes that would otherwise be described as “direct to coding.”

## Required Lifecycle

### Architect-originated plan

```text
Architect supplies complete implementation plan
  -> new planning loop at plan_review; Reviewer owns first turn
  -> Reviewer approves -> ordinary approved planning loop -> coding loop
  -> Reviewer submits findings -> plan_revision; Draftor owns next turn
  -> Draftor submits full replacement plan -> normal review cycle
```

The initial plan must meet the normal implementation-plan format, including
`## Executive Summary`, `## Context Checked`, and `## Coding Checkpoints` when
required by the current planning-loop contract. It is **Architect-originated**
and **unapproved**, never a privileged or auto-approved artifact.

### Revision planning

```text
approved planning loop + repository-contained revision sketch
  -> new ordinary planning loop with immutable source baseline
  -> Draftor produces a full replacement plan
  -> ordinary Reviewer approval -> eligible coding-loop source
```

The source loop remains historical evidence: it is never reopened, extended,
or mutated.

## Existing Seams

- `loop.host.init_loop()` and its atomic cleanup path own creation. The
  planning path currently creates `sketch.md`, tokens, session, and events;
  coding creation already demonstrates guarded source capture, fixed artifact
  copies, digest verification, and no-partial-loop rollback.
- `loop.submit.handle_submit_draft()` owns normal plan validation, versioned
  draft artifacts, `plan.current.md`, turns/events, and the transition to
  `plan_review`. Reuse its plan-format validator for Architect input rather
  than maintaining a weaker second parser.
- The planning state machine already supports the needed later handoff:
  Reviewer findings from `plan_review` advance to Draftor `plan_revision`.
  The new entry point needs only a valid initial `plan_review` state, not a
  new planning state.
- Dashboard start routes and `views/loop.js` own source selection, form
  feedback, labels, artifact order, timeline, and rendered artifact access.
  Browser checks are convenience only; server/host validation remains
  authoritative.

## Proposed Design

### 1. Model source kinds explicitly

Introduce additive, validated planning provenance rather than inferring the
source from a filename or stage:

- ordinary sketch planning — existing behavior;
- revision planning — source loop and immutable copied baseline; and
- Architect-originated draft plan — immutable initial-plan provenance.

Keep revision provenance separate from Architect-plan provenance. The former
describes historical evidence for a new Draftor-led plan; the latter describes
who supplied the initial plan under review.

Legacy sessions must project normally when these blocks are absent.

### 2. Architect-originated initial-plan capture

Provide an explicit CLI option and Dashboard mode for a repository-contained
plan file; do not overload the ordinary sketch argument or coding-loop
`--from-loop` input.

Before creating loop state, validate the path with the same safety boundary as
other governed inputs: repository containment, regular non-link file, stable
bytes, non-empty UTF-8/text policy, bounded size, and no unsafe path aliases.
Run the existing plan-content validation against those captured bytes. On any
failure, create no loop directory, token, session, or event.

On success:

- write one fixed immutable initial-plan artifact (name chosen by the plan),
  re-read and digest-check it;
- make the same bytes available as `plan.current.md` and preserve a versioned
  initial-plan artifact so artifact/timeline semantics match a normal plan
  submission;
- record source type, digest, byte size, fixed artifact identity, and the
  initial-review entry in session metadata/event history; and
- create the session directly at `plan_review`, with `next_role: reviewer`.

Do not fabricate a Draftor turn. Status, prompts, timeline, and Dashboard must
plainly say “Architect-originated draft plan — awaiting Reviewer approval,” not
“Draftor submitted.” A separate optional Architect brief remains current-loop
direction, not evidence that the plan is approved.

### 3. Revision baseline capture

From an approved **planning** loop only, accept a repository-contained
revision sketch and make a new ordinary planning loop. Under the source session
lock, capture fixed copies of:

- the approved `plan.current.md`; and
- the final approving review artifact.

Record source loop identity, fixed artifact identities, SHA-256 digests, and
byte sizes in a dedicated revision block and creation event. The copies—not
live paths to old residue—are authoritative if the source later changes or is
removed. Participants read the copied baseline and final approval review before
the revision sketch; earlier rounds and briefs are optional unless the sketch
requires them.

The Draftor writes a full replacement plan. `## Context Checked` records what
was actually consulted; it does not claim that all historical residue was read.

### 4. Surface the same provenance everywhere

CLI start/status/prompt text, Dashboard creation controls, loop header,
timeline, artifact ordering, and rendered artifact labels must distinguish:

- source baseline evidence versus current revision work; and
- an Architect-originated unapproved plan versus a Reviewer-approved plan.

Keep artifact allowlists/fixed-name validation and digest/integrity behavior
strict. Do not let metadata choose arbitrary artifact paths.

## Non-Goals

- No direct Architect-plan-to-coding-loop route.
- No automatic plan approval because the Architect wrote it.
- No reopening or mutation of a historical approved loop.
- No changes to coding-loop staged-tree approval, checkpoints, final manual
  commit handoff, or branch/worktree behavior (#54/#57).
- No requirement that participants read every source-loop round by default.

## Risks and Decisions for the Plan

- Establish exact fixed artifact names and an additive schema before touching
  UI labels; do not let implementation spread stringly source-kind checks.
- Decide whether the initial Architect-plan copy is both immutable provenance
  and `plan.current.md`, or whether a verified fixed provenance copy is paired
  with a separate mutable current projection. Preserve integrity semantics in
  either case.
- Define how the final approving review artifact is identified and copied for
  revision sources; absence or tampering must fail atomically rather than
  quietly omitting the approval evidence.
- Keep initial-plan validation identical to ordinary draft validation, including
  current/legacy checkpoint requirements, so no source kind weakens policy.
- Treat CLI and Dashboard creation contracts as one server-side operation;
  feature-name prefill for a later coding loop remains editable and is a small
  follow-on within #51, not a reason to bypass approval.

## Suggested Module Boundaries

1. **Planning-source contract and immutable capture** — input validation,
   fixed artifact copies, digest metadata, source locking, atomic rollback.
2. **Session and state-machine entry** — additive provenance projection plus
   Architect-plan initialization at existing `plan_review` semantics.
3. **CLI and participant projection** — explicit create grammar, status,
   prompts, artifact access/order, and clear role/source labels.
4. **Dashboard creation and inspection** — source selectors/actions, error
   display, history affordances, rendered evidence, and feature-name prefill.
5. **Focused contract and integration tests** — host/session/state tests,
   CLI and Dashboard API/UI coverage, integrity/atomicity/legacy regressions.

## Verification

- Architect plan: valid input starts an actionable Reviewer turn; Reviewer
  approval produces an ordinary `plan_approved` loop; findings hand off to
  Draftor `plan_revision`; no coding loop can start before approval.
- Reject malformed/missing/outside-repo/link/empty/invalid-format plan input,
  conflicting source modes, bad copies/digests, and active-loop collisions
  without leaving any new loop residue.
- Revision: only an approved planning source is accepted; source copies and
  metadata remain readable/verified after source edits or deletion; source
  loop bytes and state do not change; missing/tampered approval evidence fails
  atomically.
- Validate fixed artifact access, status/prompt/timeline wording, rendered
  Dashboard labels/order, legacy-loop projections, and shipped
  protocol/template drift protection.
- Run focused host/session/state/CLI and Dashboard loop tests for each module;
  run the broad relevant Dashboard regression suite once for completed #51,
  not after every module unless a cross-cutting contract requires it.

## Delivery Guidance

This needs a full implementation-plan review loop. It changes durable
provenance, a planning state entry point, role handoff, input trust boundaries,
CLI and Dashboard contracts, and reviewer interpretation. After approval, its
implementation should use responsibility-based coding checkpoints rather than
one monolithic coding pass.
