---
date: 2026-10-04
type: implementation-sketch
issue: 51
feature: loop-revision-planning-and-architect-plan-source
recommended-path: planning-loop-review
---

# Feature: Revision Planning from Approved Plans and Architect-Supplied Coding Plans

## Goal

Give the Architect two explicit, provenance-safe ways to establish an
implementation plan:

1. Start a **new, ordinary planning loop** from a prior approved plan plus a
   revision sketch. The new loop produces a new, self-contained approved plan.
2. Start a constrained coding loop from an **Architect-supplied implementation
   plan file** when direct-to-coding is appropriate.

These are distinct source kinds. Neither must imply that an Architect-supplied
plan passed a planning-loop review, and revising a plan must not revive or
mutate the original approved loop.

## Scope

### A. New revision planning loop

- Provide an Architect action from an approved planning loop to start **New
  revision planning loop**. This creates a new planning loop; it does not
  extend, reopen, or otherwise change the source loop.
- Require a repository-contained revision sketch. It must explicitly identify:
  - **Baseline:** the source approved loop and approved plan;
  - **Preserve:** decisions/constraints still valid;
  - **Reconsider:** the decisions or sections to change, verify, or challenge;
    and
  - **Required context:** source evidence plus charters/code to recheck.
- Capture immutable source evidence inside the new loop before creating its
  session/tokens:
  - the exact approved source plan as `source-approved-plan.md` (or an equally
    fixed, positionally validated name);
  - the source approval review/findings artifact as a second fixed artifact,
    because it is normally required reading; and
  - SHA-256, byte size, source loop ID, and source artifact identities in a
    dedicated `revision` metadata block and creation event.
- Make the source copies, not old loop paths, the authoritative baseline.
  Later source edits, removal, or loop cleanup must not alter what the new loop
  records or exposes.
- New-loop participant status/prompt text must say this is a revision planning
  loop and list the source plan and source approval review as required reading.
  The Draftor produces a full replacement plan, not a delta/amendment.
- Earlier source rounds, decision documents, and source Architect briefs are
  **not** mandatory by default. They become required only when the revision
  sketch says so or the source baseline is ambiguous. The new loop's own
  `## Context Checked` remains the record of what was actually read.
- Surface the source evidence and revision-sketch relationship in status,
  Dashboard artifact inspector, event/timeline text, and relevant participant
  handoff output. The source loop remains unchanged historical evidence.

### B. Architect-supplied implementation plan for coding loops

- Add a second coding-loop source alongside the existing approved-planning-loop
  source: a repository-contained Architect-supplied Markdown implementation
  plan file.
- CLI and Dashboard make the coding source choice explicit and mutually
  exclusive:
  - **Approved planning loop** — existing `--from-loop` path; or
  - **Architect-supplied implementation plan** — a validated plan-file path.
- Validate the supplied plan with the same trust boundary used for sketch/brief
  inputs: repository containment; regular file; no symlink or Windows reparse
  point; UTF-8; non-empty; NUL and size policy explicitly defined; read the
  validated bytes once before creation.
- Copy the supplied bytes immutably into the coding loop under a neutral fixed
  artifact name (for example `architect-plan.md`, not `approved-plan.md`),
  re-read/digest-check it, and record `source_kind: architect_plan_file` plus
  digest/size metadata. The normal Git base/tree binding still applies.
- Status, prompt, Dashboard coding header, artifact labels, and implementation
  guidance must say **Architect-supplied plan**. They must never claim planning
  approval or invent a `source_loop_id`.
- The Architect can attach a new coding-loop brief in either source mode.
  Source-brief keep/drop applies only to the approved-planning-loop source;
  the Architect-plan source has no source brief to carry forward.

## Out of Scope

- Reopening, extending, or mutating an approved planning loop to revise it.
- Treating an Architect-supplied plan as planning-loop-approved.
- Arbitrary files outside the governed repository.
- Changing coding-loop staged-tree review, approval freshness, or the normal
  post-approval manual commit handoff.
- Multi-draftor, observer, model-identity, or competitive-loop features.

## Existing Seams and Constraints

- `loop/host.py` already has the guarded coding successor path:
  `init_loop(..., mode="coding", from_loop=...)`, `_read_approved_source()`,
  and `_init_coding_loop()`. It validates the source inside the source session
  lock, snapshots Git, writes an immutable plan copy, verifies its digest, and
  creates the session/events atomically under the single-active-loop lock.
  Reuse these ordering and rollback patterns; do not build parallel unsafe
  creation flows.
- `loop/session.py`, `loop/submit.py`, and `loop/cli.py` project and consume
  coding provenance/brief metadata. Additive fields must preserve old planning
  loops and existing coding loops with `source_loop_id` / `approved-plan.md`.
- Dashboard `views/loop.js` already has a planning-vs-coding create form,
  approved-loop picker, source-brief selection, coding header, and artifact
  ordering. It must display source kind without hiding integrity failures or
  treating a supplied file like an approved-loop artifact.
- The loop route/server remains authoritative for containment, validation,
  token issuance, and atomic creation. Browser validation is early feedback
  only.
- The revision source is a **planning** provenance boundary, not a coding
  source. Keep its metadata separate from the coding block so stage/mode
  semantics stay unambiguous.

## Design Questions for the Plan

1. Define the minimal additive session schema for `revision` and coding
   `source_kind`, including strict status allowlists and backward compatibility.
2. Define fixed names and verification helpers for `source-approved-plan.md`,
   the source approval-review copy, and the neutral Architect-plan copy. Do not
   trust filenames or paths read from arbitrary session metadata.
3. Decide the exact CLI grammar without overloading `--from-loop`: likely a
   dedicated revision-source argument for planning starts and a dedicated
   `--plan-file` argument for coding starts. Both CLI and Dashboard must reject
   conflicting/missing selections before side effects.
4. Decide whether a revision loop has its own optional Architect brief only,
   or explicitly offers source-brief carry-forward. Default to no automatic
   carry-forward unless the sketch requires it; the sketch itself is the new
   Architect direction.
5. Define Dashboard entry points and labels: approved-loop history action for
   revision; source-type selector for coding creation; artifacts/status that
   distinguish baseline evidence, current sketch/plan, and Architect plans.

## Suggested Module Boundaries

1. **Source validation and immutable capture** — shared, narrowly scoped
   helpers in the loop host/session boundary for safe file bytes, fixed-name
   copies, digest verification, and atomic rollback. Preserve the existing
   source-session-lock and single-active-loop ordering.
2. **Session/provenance projection** — additive metadata, strict status views,
   events, CLI/prompt rendering, and artifact allowlists for revision sources
   and coding source kinds. This is one contract; do not scatter labels or
   infer source kind from filenames.
3. **Creation surfaces** — CLI arguments plus Dashboard revision action and
   source selectors. They translate UI/arguments into the same server-side
   source contract and show actionable validation errors.
4. **Dashboard inspection and tests** — source evidence labels/artifact order,
   integrity display, stale-selection handling, and end-to-end coverage. Keep
   styling local to existing Loop workspace patterns.

## Verification Focus

### Revision planning

- A valid approved planning loop plus revision sketch creates a separate normal
  planning loop; the old loop's session, stages, rounds, and artifacts remain
  byte-for-byte unchanged.
- The new loop has digest-pinned copies of the final approved plan and approval
  review. Source edits/deletion after creation do not affect new-loop reading,
  status, or prompts.
- Invalid source IDs, non-approved/non-planning sources, absent approval review,
  unsafe sketch paths, digest/copy mismatch, and a concurrent active loop fail
  before any partial loop is left behind.
- Status/prompt/Dashboard distinguish baseline artifacts from the new sketch
  and plan; they require only the minimum baseline context by default.

### Architect-supplied coding plan

- Existing `--from-loop` coding starts remain byte-for-byte compatible in
  provenance, brief behavior, artifact name, and prompts.
- A safe Architect plan file creates a coding loop with neutral artifact name,
  `source_kind: architect_plan_file`, immutable digest-pinned bytes, and normal
  Git base/tree binding.
- Both/neither source selection, outside-repo paths, symlinks/reparse points,
  directories, empty/non-UTF-8/NUL/oversize files, copy failure, and active
  loop collisions fail atomically.
- Dashboard creation/status/prompt/artifact views visibly distinguish the two
  source kinds; source-brief controls are unavailable/inapplicable for the
  Architect-plan path.

### Regression and governance

- Run loop host/session/CLI tests, Dashboard loop coding/brief/UI tests, source
  path and atomic-failure tests, and the full relevant dashboard suite.
- Update loop, Dashboard server/UI, and cross-cutting charters immediately with
  the code. Add release/changelog and commit-draft evidence only after the
  behavior and tests are complete.

## Planning-Path Assessment

**Use an implementation planning loop.** This feature changes durable
provenance, immutable artifact trust boundaries, participant context, CLI and
Dashboard creation/inspection flows, and backward-compatible session status.
It has material design choices around source metadata, fixed artifacts, and
brief carry-forward. Direct-to-coding would compress those decisions into
implementation and make the security/governance boundary harder to review.
