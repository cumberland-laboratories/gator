# Commit Pipeline

## What This Page Is

This page explains the end-to-end commit pipeline in Gator at a human/system level.

It is not a charter and not a line-by-line code reference.

It is the Architect-facing explanation of:

- what happens when an agent runs `git commit`
- what is enforced versus advisory
- which files and modules participate
- where the live implementation currently lives
- where the known fragile edges are

## Why This Exists

The commit pipeline is one of Gator's core product surfaces.

It is also easy to lose track of because the behavior is spread across:

- git hook wrappers
- `.gator/scripts/gator-pre-commit.py`
- `.gator/scripts/enforcer-review.py`
- trailer/status/session files under `.gator/`
- multiple charter surfaces
- both live and template copies of the same scripts

If the Architect cannot answer "what happens on commit?" without reading source, the system is too slippery.

This page is meant to be the starting point.

## Current State

Status: `Implemented`, with active refinement.

The commit pipeline is real and operational today. It is not a planned feature.

The main moving parts are:

- deterministic pre-commit validation
- commit message trailer assembly
- post-commit cleanup and rolling session logging
- optional enforcer review as a separate advisory path
- charter-surface resolution that differs between the source command-post repo and ordinary governed repos

Recent work tightened:

- cross-cutting charter enforcement
- source-vs-governed charter surface resolution
- INDEX-based required-charter checks
- integration between the live scripts and the starter template copies

## The User-Facing Flow

From the Architect or agent perspective, a normal commit looks like this:

1. The agent prepares `.gator/commit_draft.md`.
2. The agent stages code and governance changes.
3. `git commit` triggers the hook pipeline.
4. Pre-commit validation either blocks or passes.
5. If validation passes, commit-msg appends `Gator-*` trailers.
6. After the commit lands, post-commit cleanup resets working governance state and appends to the rolling active session log.

If validation blocks:

- the commit is rejected
- findings are written to `.gator/whiteboard.md`
- dangerous-pattern lint findings are written to `.gator/commit_issues.md`
- status is written to `.gator/status.json`
- an Architect approval path may be opened via override request files

## The Three Hook Phases

### 1. Validate (`pre-commit`)

Entrypoint:

- `.gator/scripts/hooks/pre-commit`
- calls `.gator/scripts/gator-pre-commit.py --phase validate`

Purpose:

- deterministic governance gate
- may block the commit

What it checks:

- `commit_draft.md` exists and parses
- code changes are accompanied by required charter changes
- required charters are derived from the authoritative `INDEX.md`
- dangerous-pattern lint runs on added lines
- warnings are computed for softer governance signals

Primary outputs:

- `.gator/status.json`
- `.gator/whiteboard.md`
- `.gator/commit_issues.md` when lint findings exist

Blocking examples:

- code changed but no required charters are staged
- required cross-cutting charter is missing from staged files
- malformed or empty commit draft
- high-severity lint finding

### 2. Trailers (`commit-msg`)

Entrypoint:

- commit-msg hook wrapper
- calls `.gator/scripts/gator-pre-commit.py --phase trailers <msg-file>`

Purpose:

- assemble the full commit message from `commit_draft.md` when it has real content
- append portable `Gator-*` trailers to the commit message

When `commit_draft.md` has a populated `message` field or non-stub body content, the commit-msg phase replaces the entire commit message with content assembled from the draft. The `message` frontmatter field becomes the summary line; the session change log entries (minus the `# Session Change Log` heading) become the body. Trailers are appended after. If the draft is empty or stub-only, the agent's `-m` message is preserved (backward compatible).

What it uses:

- `.gator/status.json`
- `commit_draft.md` (source of truth for commit message content)
- current staged reality
- any approved override metadata

Examples of trailer payload:

- charter count
- thread count
- change type
- significance
- whether charter changes were staged or override-approved

This is how governance metadata and the session change log travel with commit history.

### 3. Cleanup (`post-commit`)

Entrypoint:

- post-commit hook wrapper
- calls `.gator/scripts/gator-pre-commit.py --phase cleanup`

Purpose:

- clear transient working state after a successful commit
- preserve a lightweight local rolling session log

What it does:

- appends the latest commit to `.gator/sessions/_active/*.md`
- resets `.gator/commit_draft.md` to the blank stub

Important boundary:

- this does **not** mint a new committed session summary on every commit
- rolling active session logs are local working artifacts, not the durable audit trail

## What Blocks a Commit

The most important blocking rule is:

code changes must land with the required charter changes.

This used to rely too heavily on heuristics like "did we add a cross-module import?"

The stronger current model is:

- resolve the authoritative charter surface for this repo
- read its `INDEX.md`
- determine which charters the changed files require
- block if the required charters are not staged

That means the system can now say:

- not just "a charter is missing"
- but "these specific charters are required, and these are missing"

The rule name you will often see is:

- `charter-alongside-code`
- `charter-index-gap`

## What Is Advisory Rather Than Blocking

Some governance checks warn but do not block.

Examples:

- missing significance assessment
- missing decision tags
- tripwire-touched warnings
- new functions not yet documented in charters
- lower-severity lint findings

These still matter. They are written into the Architect-visible surfaces, but they do not stop the commit by themselves.

## Architect Override Flow

Gator supports a two-phase Architect-approved override for charter-gate failures.

The intended flow is:

1. Hook blocks and writes `.gator/override-request.json`
2. Architect reviews the findings
3. Architect runs approval flow via `gator-approve.py`
4. Agent retries the commit
5. Hook validates the approval and consumes it one-shot

Important product point:

- the agent is not supposed to self-approve
- override metadata is recorded into trailers and whiteboard output

This keeps the exception path visible instead of becoming an invisible bypass.

## Files Written by the Pipeline

Working governance state:

- `.gator/status.json`
- `.gator/whiteboard.md`
- `.gator/commit_issues.md`
- `.gator/override-request.json`
- `.gator/override-approved.json`
- `.gator/.override-meta.json`
- `.gator/commit_draft.md`

Rolling local session state:

- `.gator/sessions/_active/*.md`

Portable commit history state:

- `Gator-*` trailers appended to the commit message

## Source of Truth Modules

Primary live implementation:

- `.gator/scripts/gator-pre-commit.py`
- `.gator/scripts/enforcer-review.py`
- `.gator/scripts/gator-approve.py`

Installed hook wrappers:

- `.gator/scripts/hooks/pre-commit`
- commit-msg hook wrapper
- post-commit hook wrapper

Template copies that define what governed repos receive:

- `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
- `src/gator_command/templates/gator-starter/scripts/enforcer-review.py`
- `src/gator_command/templates/gator-starter/scripts/hooks/*`

Shared resolver:

- `src/gator_command/scripts/gator_core.py`
- specifically `resolve_charter_surface(repo_root)`

## Charter Surfaces: Why This Gets Confusing

The commit pipeline has to operate across two governance topologies.

### Source command-post repo

This repo, `gator-command`, is special.

For shipped command-post/product code, the authoritative charter surface is:

- `.gator/charters/`

Its cross-cutting charter is:

- `scripts-cross-cutting.md`

### Governed repos

Ordinary governed repos, including deployed/public-style repos, use:

- `.gator/charters/`

Their cross-cutting charter is:

- `cross-cutting.md`

### Product requirement

The hook and enforcer must not guess this ad hoc in ten places.

They should resolve it through the shared resolver in `gator_core`.

That is now an explicit cross-cutting contract.

## Relationship to Enforcer Review

The enforcer is not the blocking pre-commit gate.

The split is:

- `gator-pre-commit.py`: deterministic, local, blocking
- `enforcer-review.py`: richer advisory review, optionally model-backed

The enforcer can:

- run Layer 1 mechanical lint
- run charter-grounded review
- use structural priors from `gator-charter-verify`
- append findings to `.gator/whiteboard.md`

It is best understood as a second governance surface, not as the same thing as the hook.

## Relationship to Charters

The most relevant charters for this feature are:

- `.gator/charters/scripts-command-post.md`
- `.gator/charters/scripts-cross-cutting.md`
- `.gator/charters/commit-gate.md`
- `.gator/charters/cross-cutting.md`

Why more than one?

- source repo behavior is governed by `.gator/charters/`
- self-governed/public-style behavior is governed by `.gator/charters/`

This is one reason the feature can feel slippery if you only read one layer.

## Live vs Template Copies

This is one of the most important implementation facts.

There are usually two versions of the hook/enforcer code that matter:

- live copy in `.gator/scripts/`
- shipped template copy in `src/gator_command/templates/gator-starter/scripts/`

If they drift, the source repo may behave correctly while new governed repos receive older behavior.

For that reason, template sync is itself part of the product contract.

## Known Fragile Areas

These are the places the Architect should keep watching:

### 1. INDEX quality

The stronger charter gate now depends on `INDEX.md` being accurate.

If a file is not mapped correctly in the authoritative index:

- the hook cannot require the right charters mechanically

### 2. Live/template drift

A fix in `.gator/scripts/` is not enough if the starter template copy is not updated too.

### 3. Source-vs-governed charter surface confusion

If a tool reads `.gator/charters/` when it should read `.gator/charters/`, or vice versa, the gate can give false confidence.

### 4. Architect-facing legibility

Even when the code is correct, the feature becomes hard to manage if the only explanation is spread across charters and implementation.

That is exactly why this page exists.

## High-Level Mental Model

If you want the shortest accurate picture, it is this:

- the hook is a deterministic governance gate
- it checks staged reality against required charter updates
- it records machine-readable and Architect-readable state
- it appends portable metadata to commits
- it resets local working governance state after success
- it relies on accurate charter-surface resolution and accurate `INDEX.md` routing

## Where To Read Next

For module ownership and implementation detail:

- `.gator/charters/scripts-command-post.md`
- `.gator/charters/scripts-cross-cutting.md`
- `.gator/charters/commit-gate.md`

For broader product framing:

- `docs/architecture.md`
- `docs/governance-model.md`
- `docs/enforcer-patterns.md`

For archaeology and audit context:

- `docs/session-archaeology.md`
