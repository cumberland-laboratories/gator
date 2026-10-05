---
date: 2026-09-30
type: implementation-sketch
issue: "#41"
title: "Coding loop with diff-aware implementation review"
---

# Coding Loop with Diff-Aware Implementation Review

## Goal

Extend Gator Loop from planning-only debate into an optional **coding mode**. A coding loop begins from an approved planning artifact, lets the Draftor implement staged work, and lets the Reviewer assess the actual candidate tree—not merely a prose summary. It ends with a clear handoff back to the Draftor for one ordinary, Architect-confirmed Git commit.

## Core workflow

1. The Architect starts a distinct coding loop from an approved plan/plan loop and records a Git base commit.
2. The Draftor changes code, required charters, and `commit_draft` material; runs relevant checks; and stages the intended candidate change.
3. The Draftor submits a versioned implementation artifact, for example `implementation.round-1.md` and `implementation.current.md`.
4. The CLI captures the review binding facts itself: base HEAD, current HEAD, staged-tree OID, changed paths, and whether unstaged residue exists.
5. The Reviewer reads the implementation artifact, required charters, and the actual staged diff/tree. Findings use the existing review format, but record the reviewed staged-tree OID.
6. `APPROVE` means the exact reviewed staged tree is ready for the existing normal commit workflow. It does not create a commit.
7. The Draftor returns to its ordinary model session and creates one normal Git commit, using existing repository hooks and the normal Architect confirmation. If the staged tree changes after approval, it must return to implementation review.

## Draft artifact contract

Require the same `## Executive Summary` convention as planning artifacts plus:

- `## Implementation Summary` — behavior changed and key files/functions.
- `## Charter Updates` — relevant charter sections/tripwires and how they were checked.
- `## Verification` — commands run, results, and known gaps.
- `## Commit State` — CLI-captured base/current HEAD, staged-tree OID, changed-path summary, and unstaged-residue status.

The artifact is concise evidence and orientation. The Git facts are independently captured and validated by the loop CLI; prose never substitutes for the actual tree.

## Review and binding rules

- The Reviewer must inspect the staged diff/tree corresponding to the submitted tree OID, plus the affected charters.
- Reviewer findings/approval persist the reviewed tree OID.
- A tree mismatch blocks approval or marks a prior approval stale. The Dashboard must make this obvious.
- A later implementation submission creates the next reviewable tree generation; no intermediate Git commit is required or desired.
- Existing escalation, pause, unblock, bounded wait, and loop-resume behavior should carry over unless a coding-specific distinction is necessary.

## State and Dashboard direction

Add a mode discriminator rather than mutating planning-loop semantics. Illustrative coding stages:

- `implementation_drafting`
- `implementation_review`
- `implementation_revision`
- `implementation_approved`

The Dashboard should link back to the approved plan and display the implementation round, base/current/reviewed/staged identifiers, changed-path summary, verification summary, reviewer verdict, and a visible stale-review warning. On approval, show an explicit handoff: **return to the Draftor session for one normal commit**.

## Commit protocol

Do not create one commit per loop round. Do not add a `gator loop commit` wrapper, Dashboard commit authorization, or new Git-hook bypass. The existing commit workflow remains authoritative:

1. Reviewer approves the exact staged candidate.
2. Draftor makes one normal commit under existing hooks and Architect confirmation.
3. If code changes before that commit, the Draftor resubmits it for review.

Potential later work may add durable loop-to-commit linkage if live use shows that the manual handoff is insufficient; it is not part of this MVP.

## Important boundaries and risks

- **Planning compatibility:** existing planning loops must remain behaviorally unchanged.
- **Tree authority:** Git facts and staged tree are authoritative for implementation review; loop artifacts describe them.
- **Unstaged residue:** surface it prominently; decide whether it blocks approval outright or is an explicit Architect/Reviewer warning with a narrowly defined policy.
- **Recovery:** persisted base/tree bindings must survive Dashboard or process restart without treating stale approval as current.
- **Git portability:** worktrees, unborn/no-commit repositories, merge/conflict states, and unavailable Git should fail clearly rather than yield a misleading tree binding.
- **Scope control:** this is governed review and handoff, not a general CI system, merge queue, or replacement for Git commits.

## Suggested modular implementation shape

1. Define coding-loop mode/schema and state-machine transitions, with planning-mode regression coverage.
2. Add a small Git snapshot helper for base/current/staged-tree and changed-path facts, including clear degraded/error results.
3. Add implementation artifact submission and tree-binding validation.
4. Add implementation review/approval plus stale-tree detection.
5. Add Dashboard display and explicit final-commit handoff.
6. Add end-to-end/recovery tests: clean approval, changed-after-review rejection, multi-round revision, interruption/restart, and unchanged planning-loop behavior.

## Questions for the planning loop to resolve

1. Must unstaged residue block implementation submission/approval, or can it be disclosed while the staged tree remains the sole reviewed candidate?
2. How should a coding loop reference the approved plan: immutable copied artifact, source loop ID + artifact digest, or both?
3. Is the base commit captured when the coding loop starts, or when the first implementation is submitted—and how should branch movement be displayed?
4. What exact condition marks approval stale: staged-tree OID only, or staged-tree plus HEAD/base/changed-path facts?
5. Should coding mode be a separate command/mode at loop creation, or a guarded successor operation from an approved planning loop?
