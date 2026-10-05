---
date: 2026-10-04
type: implementation-sketch
issue: 55
feature: coding-loop-modular-checkpoints
---

# Feature: Modular Checkpoints and Incremental Code Review in Coding Loops (#55)

## Goal

Make a coding loop review real code at the responsibility-based checkpoints
defined by its approved implementation plan, instead of allowing the Draftor
to implement the entire plan before the first Reviewer handoff.

The workflow remains one normal final commit. Checkpoint review operates on the
staged worktree; it does not create a commit per module.

```text
approved planning loop
  -> coding loop, checkpoint 1 drafting
  -> Draftor submits checkpoint-1 evidence + staged candidate
  -> Reviewer reviews the exact checkpoint-1 diff
       -> approve: checkpoint 2 becomes actionable
       -> findings: Draftor revises checkpoint 1
  -> ...
  -> Reviewer approves final checkpoint
  -> return to Draftor for one normal commit of the final staged tree
```

## Scope

### 1. Approved-plan checkpoint contract

- Add a compact, explicit `## Coding Checkpoints` section to the
  implementation-plan format. It names ordered checkpoints by responsibility,
  not by files or arbitrary elapsed time.
- Each checkpoint must state its purpose/scope and focused verification. It
  may reference one or more plan changes/modules; it must not duplicate the
  whole plan.
- New plans intended for multi-step coding loops should declare checkpoints.
  For compatibility, an older approved plan with no checkpoint section creates
  one implicit `Full implementation` checkpoint rather than becoming
  unusable.
- The Reviewer of the planning loop checks that checkpoints are meaningful:
  no styling/tests/docs-only pseudo-modules; no file-count slicing; no
  unexplained tests. This applies the existing
  `writing-implementation-plans.md` procedure.

### 2. Durable coding-loop checkpoint state

- At coding-loop creation, parse and freeze a small checkpoint manifest from
  the immutable approved plan. Persist the ordered ids/titles, current
  checkpoint, per-checkpoint review state, and the predecessor accepted tree.
  Do not re-parse a mutable working copy later.
- Reuse the existing coding stages (`implementation_drafting`,
  `implementation_review`, and `implementation_revision`) rather than adding
  a second state machine. Their prompt/status/timeline meaning becomes
  "for checkpoint N".
- A Reviewer approval of a non-final checkpoint records its accepted staged
  tree and advances the Draftor to the next checkpoint. Only approval of the
  final checkpoint produces `implementation_approved` and the existing
  one-commit handoff.
- Findings return the Draftor to the same checkpoint. Define whether the
  existing round ceiling is per checkpoint (preferred) or global; the plan
  must make the choice explicit and keep max-round/extend behavior coherent.

### 3. Exact diff and evidence boundaries

- Each implementation submission records the current checkpoint identity,
  its starting/previously accepted tree, the submitted staged tree, changed
  paths, focused tests, and the Draftor's concise implementation evidence.
- The Reviewer command/prompt must show the immutable exact diff for that
  checkpoint: `git diff <checkpoint-base-tree> <candidate-staged-tree>`.
  The cumulative final tree remains the thing that is ultimately committed.
- A later checkpoint may legitimately touch a previously approved file. It
  must disclose that dependency and be reviewed as part of the later
  checkpoint; do not impose a brittle file-ownership prohibition.
- Existing staged-tree freshness rules remain mandatory. An approval only
  authorizes the exact staged tree reviewed. No per-checkpoint commit, reset,
  automatic stash, or hidden worktree mutation.

### 4. Participant and Architect experience

- Draftor prompts name the active checkpoint, its scope, required plan
  context, predecessor tree, and the expected evidence/test focus.
- Reviewer prompts state explicitly that real code changed and identify the
  checkpoint-specific diff command, not just an implementation summary.
- Dashboard status, timeline, artifact labels, and coding region show
  checkpoint number/title/state, candidate tree, and prior checkpoint
  approvals without raw Markdown excerpts.
- Architect can inspect checkpoint progress but does not manually advance it.
  Existing pause, unblock, blocked-state, attention, and end behavior must
  preserve the active checkpoint and resume the correct role.

## Constraints and Related Work

- #51's revised direction is a prerequisite for the *future* Architect-plan
  path: all coding loops originate from a Reviewer-approved planning loop.
  #55 must continue to work for the existing approved-plan coding source now.
- #54/#57 establish the clean-worktree and dedicated branch/worktree
  lifecycle. This feature must not infer ownership from file paths or absorb
  unrelated changes; its checkpoint diffs are staged-tree evidence only.
- #53's durable blocked state must keep the participant connected through a
  checkpoint block or re-escalation.
- Keep the current manual return to the Draftor session for the final commit.

## Likely Seams

- `loop/state_machine.py`: checkpoint-aware coding transitions while retaining
  the established stages and terminal approval semantics.
- `loop/host.py` / `loop/session.py`: parse/freeze checkpoint manifest at
  coding-loop creation; additive session schema and strict status projection.
- `loop/submit.py` / `loop/gitsnap.py`: checkpoint base/candidate snapshots,
  implementation/review artifact sections, freshness, round behavior.
- `loop/cli.py` and participant protocol/artifact-format document pairs:
  checkpoint-aware action text, exact diff guidance, required evidence.
- `gator-dashboard.py`, `dashboard/views/loop.js`, and local CSS: creation
  guard/status serialization, checkpoint progress/timeline/artifact display.

## Verification Focus

- A two-checkpoint plan prevents checkpoint 2 submission before checkpoint 1
  approval; approval advances it without a Git commit.
- Review findings keep the loop on the same checkpoint and preserve its base
  tree; a resubmission records a new candidate against that base.
- The Reviewer sees and approves/rejects the checkpoint-specific immutable
  diff, including when a later checkpoint revisits an earlier file.
- Final approval is impossible before the final checkpoint and still requires
  live staged-tree freshness; one normal final commit completes the handoff.
- A plan with no checkpoint section follows an explicit one-checkpoint
  compatibility path.
- Checkpoint state survives Dashboard refresh, pause/unblock, blocked-state
  resolution, and terminal/reopen behavior without allowing the wrong role or
  checkpoint to proceed.
- UI tests cover progress, labels, no mutation on identical polls, stale
  responses, and accessible text—not color-only indicators.
- Keep tests proportionate: parameterize equivalent transition/rejection
  cases, reuse existing staged-tree and Dashboard suites, and add a focused
  test only for each new checkpoint invariant.

## Planning-Path Guidance

Use a full implementation planning loop before coding. This is not merely a
procedure update: it changes durable coding state, lifecycle transitions,
artifact/provenance rules, reviewer authority, CLI/Dashboard contracts, and
the relationship between staged diffs and the eventual single commit.

The resulting plan should have responsibility-based implementation modules,
not a separate module for every file, document pair, style rule, or test
suite. It should settle the checkpoint grammar, per-checkpoint vs global round
budget, and exact checkpoint-base-tree semantics before implementation starts.
