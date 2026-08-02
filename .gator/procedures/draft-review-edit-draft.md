# Procedure: Draft - Review - Edit - Draft

## Purpose

This procedure defines how agents and the Architect should evolve feature designs and planning documents in Gator.

The core rule is:

- do **not** create `v1`, `v2`, `v3` copies for ordinary design evolution
- do **not** shuttle large blocks of text back and forth between models by copy/paste
- use **one working document**, edited in place
- use **Git commits** as the version history

Gator Dashboard is already designed to show this progression through diffs, commit history, and file history. The commit log is the changelog.

## Why This Exists

A mutable working document in Git is better than:

- a shared whiteboard
- parallel `v1` / `v2` / `final-final` files
- the Architect copying one model's review into another model's chat

Editing the same document in place preserves:

- continuity
- context
- design history
- auditability
- reviewability

It also makes the progression visible in Dashboard:

- initial draft
- critique
- revision
- rewrite
- narrowed scope
- final implementation direction

That is the intended workflow.

## The Rule

For blueprints and active planning documents:

- the file itself is the working surface
- commits are the version history
- review happens against the current file
- revisions are edits to the same file

The workflow is:

1. Draft the document
2. Commit it
3. Append the review to the document
4. Commit the reviewed state
5. Revise the same document back into a clean current draft
6. Commit the revision
7. Repeat until ready

This is the `draft - review - edit - draft` loop.

## The Review Cycle

The important nuance is that the working document alternates between:

- a **clean current draft**
- a **review-appended state**

The intended sequence is:

1. Draft the document
2. Commit it
3. Review the document and append the review at the bottom
4. Commit that reviewed state
5. Revise the document into a clean new draft
6. Commit the revision
7. Review again and append the new review
8. Commit that reviewed state
9. Repeat as needed

In shorthand:

- draft, commit
- append review, commit
- revise clean draft, commit
- append review, commit
- repeat

This matters because the review itself is worth preserving in history, but the main working document should return to being a clean design artifact after each revision pass.

The review is part of the progression.
It is not meant to permanently clutter the current draft.

This cadence is the strongest default for:

- implementation plans
- architecture plans
- boundary memos under active refinement

For blueprints, use it as guidance rather than a rigid rule.

Blueprints are often more exploratory:

- larger rewrites are normal
- sections may be restructured aggressively
- some review points may be absorbed directly into the next draft

The core rule still holds:

- one working document
- edits in place
- commits as version history

But blueprints do not always need to preserve an appended-review block in as literal a way as plans do.

## Where This Applies

### Blueprints

Blueprints are the clearest case.

They are living feature-design documents. They should normally be:

- created once
- revised in place
- reviewed in place
- rewritten in place if needed

Do **not** create:

- `feature-blueprint-v2.md`
- `feature-blueprint-revised.md`
- `feature-blueprint-final.md`

unless there are intentionally two competing blueprints that must coexist as separate alternatives.

### Planning artifacts

Artifacts are usually deeper and more frozen than blueprints, but some artifacts are active planning documents rather than archival records.

For an active planning artifact, the same rule applies:

- keep one working document
- revise it in place
- let commits record the progression

Examples:

- implementation plans
- architecture sketches still under active refinement
- boundary memos that are being sharpened over several reviews

### Frozen research or historical records

This procedure does **not** mean every artifact becomes mutable forever.

Some artifacts are meant to remain frozen snapshots:

- external analysis captured at a point in time
- market review tied to a date
- historical decision record
- imported conversation or transcript summary

Those should remain date-stamped records unless there is a strong reason to convert them into a living document.

## Default By Document Type

Use these defaults:

| Document type | Default mode |
|---|---|
| `blueprints/` | Living document, revised in place |
| Active implementation/design artifact | Living document, revised in place |
| Research artifact / external analysis / historical snapshot | Frozen record |
| Thread | Living lightweight note |

If there is doubt, ask:

- is this document meant to guide upcoming work?
- or is it meant to preserve what was known at a moment in time?

If it guides upcoming work, prefer the living-document model.

## Why Not Add A Separate `plans/` Tier

Do not add a new `plans/` directory just to support revision history.

Reasons:

- the existing topology already has strong roles for blueprints, artifacts, threads, and procedures
- revision history is already handled by Git
- Dashboard already exposes that history well
- a new tier would add categorization overhead without solving a new problem

The problem here is not missing storage. The problem is documenting the working method.

The method is:

- edit the document
- commit the change
- let Git and Dashboard tell the story

## Review Workflow Across Multiple Models

When multiple models are involved:

- the reviewer should review the current document
- the revising agent should edit the same document
- the Architect should not need to relay long text blobs between models manually

The document is the handoff surface.

That means:

- model A drafts the blueprint
- model B reviews the blueprint
- the review is appended and committed
- model A or model C revises the blueprint back into a clean current draft
- commit history captures the exchange

The file absorbs the conversation.

This is better than model-to-model copy/paste because:

- the review is attached to a real artifact
- the revision is visible as a diff
- the outcome is not trapped in chat text

## Allowed Operations

Revising in place may include:

- line edits
- section additions
- section deletions
- structural reordering
- complete rewrites

All of these are acceptable because the old state remains available in Git history.

There is no need to preserve obsolete text in the current file just to keep a record. That is what commits are for.

Likewise, there is no need to leave every prior review appended in the current draft forever. Preserve the reviewed state in Git, then clean the document back to its latest working form.

## When A New File *Is* Appropriate

Create a new file only when one of these is true:

- there are two intentionally competing alternatives that should coexist
- the original document is now a frozen historical record and a new phase needs a new working surface
- the topic changed enough that the old title and scope are no longer honest
- the old document should remain citeable as a point-in-time artifact

Good examples:

- `command-post-architecture-option-a.md` and `command-post-architecture-option-b.md`
- a dated market snapshot that should remain frozen, followed later by a new dated snapshot

Bad examples:

- `feature-plan-v2.md`
- `feature-plan-final.md`
- `feature-plan-latest.md`

## Commit Guidance

Because the file is revised in place, commit messages matter.

Each commit should describe what changed in the design, for example:

- tighten session-summary cache model
- shift transcript pipeline to local DB first
- split public audit from paid compliance packaging
- resolve freshness invalidation approach

Review commits should also be explicit, for example:

- append review to session summary aggregator plan
- append second review to transcript DB architecture
- revise blueprint after Codex findings

This makes Dashboard history readable as a design log.

## Dashboard Implication

This procedure assumes Dashboard is the primary history reader.

The value is:

- the current document is easy to find
- the version progression is in commits
- the Architect can inspect the changelog without opening a pile of near-duplicate files

This is one of Gator's strengths:

- governed design progression, not just governed code progression

## Bottom Line

For blueprints and active plans:

- keep one document
- revise it in place
- commit each meaningful change
- let Git history and Dashboard provide the versions

The working document is the present state.
The commit history is the design history.
