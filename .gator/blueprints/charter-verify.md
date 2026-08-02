# Charter Verify

## What This Page Is

This page explains `gator-charter-verify.py` as a system feature.

It is for the Architect question:

"What does charter verify actually do, where is it used, and why does it matter?"

It is not a charter and not a code walk.

It is the human-readable description of the feature's role in the Gator product.

## Why This Exists

`gator-charter-verify.py` is one of the most important integrity tools in Gator, but it is easy to misread.

It is not:

- a charter linter
- a commit hook
- an enforcer replacement

It is a **structural verifier**.

Its job is to compare code structure against existing charter structure and emit cheap mechanical findings that tell the human or enforcer where drift is likely.

That makes it a key anti-slippage feature.

## Current State

Status: `Implemented`, actively improving, increasingly integrated into the governance loop.

The feature exists today and runs successfully as a standalone tool.

Its importance has increased because it is no longer just a manual utility. It now feeds the enforcer-review pipeline as a source of structural priors.

## Core Product Role

The shortest accurate description is:

`gator-charter-verify.py` checks whether the charter layer still plausibly matches the code layer.

It does not decide materiality.

It tells you:

- where coverage may be missing
- where a charter may be stale
- where a file may be under-documented
- where cross-cutting treatment may be missing

Then the enforcer or Architect decides what matters.

## What It Checks

The verifier emits findings in a small set of named classes.

### `coverage-gap`

A tracked source file is not covered by any charter.

This answers:

- "Is there code with no governing charter at all?"

### `function-gap`

A public function exists in code but is not represented in any charter.

This answers:

- "Did we add behavior without documenting it?"

### `complexity-mismatch`

A file looks structurally nontrivial, but the charter coverage appears unusually thin.

This answers:

- "Does this charter look suspiciously shallow for what the code now does?"

### `stale-structure`

A charter references functions that no longer exist or no longer match the code structure.

This answers:

- "Is the charter telling an outdated story?"

### `cross-cutting-suspect`

A file has high import fan-out or suspicious cross-module complexity without corresponding cross-cutting treatment.

This answers:

- "Is this starting to behave like a cross-cutting area without the governance acknowledging it?"

## What It Does Not Do

This tool is deliberately narrower than the enforcer.

It does not:

- decide whether a finding is materially bad
- understand Architect intent
- rewrite charters
- block commits directly
- perform model judgment

It is a mechanical verifier, not a policy arbiter.

## Where It Fits in the Stack

The feature sits between charter generation and enforcer review.

The stack is roughly:

1. code exists
2. charters exist
3. `gator-charter-verify.py` checks structural alignment
4. enforcer-review consumes those findings as cheap priors
5. Architect or enforcer judges materiality

That middle position is why it matters so much.

It is the low-cost "something looks off here" detector.

## How It Works

At a high level, the verifier does five things:

1. discovers the source files that are charter-relevant
2. discovers the charter directories that govern the repo
3. parses charter structure
4. analyzes source-file structure using the same analyzers as charter-draft
5. emits structural findings by comparing the two

## Input Surfaces

### Source files

The verifier uses the same discovery and language analyzers as `gator-charter-draft.py`.

That matters because it keeps:

- "what draft sees"
- "what verify sees"

on the same structural basis.

### Charter files

It parses all applicable charters and extracts:

- `Covers:` file mappings
- documented function entries
- `File:` references associated with entries

This is the basis for coverage and stale-structure checks.

### Repo topology

The verifier knows about both charter domains:

- `.gator/charters/`
- `.gator/charters/`

That is important in command-post/source-repo contexts where both can exist.

## Why `File:` Lines Matter

One of the more important implementation details is that stale-structure checks use `File:` lines to map charter entries back to source files.

That means:

- a charter entry with a `File:` line can be checked more precisely
- entries without `File:` are intentionally treated more conservatively

This avoids a lot of false positives in larger or multi-file charters.

## Where It Is Used

### 1. Standalone structural audit

You can run it directly to inspect charter/code drift.

Typical use:

- "Show me the current structural gaps in this repo"

### 2. Enforcer-review structural priors

This is the most important current integration.

`enforcer-review.py` now tries to locate `gator-charter-verify.py`, runs a full-repo verify pass, then filters the findings down to the changed files before passing them into the model prompt as **structural priors**.

This means the model no longer starts cold.

It begins with cheap mechanical hints such as:

- this file may have a function gap
- this charter may be stale
- this file may be uncovered

That is a major improvement in review focus.

### 3. Architect mental model support

Even when no model is involved, the verifier is the fastest way to ask:

- "Which parts of the charter map are probably drifting?"

That is why it is strategically important.

## How It Has Improved

The biggest improvement is not just in the verifier itself. It is in how the rest of the system now uses it.

### Before

It was easier to think of charter-verify as an isolated maintenance utility.

Useful, but optional.

### Now

It is part of the review loop.

The enforcer:

- locates it automatically
- runs it cheaply
- filters its findings to the changed files
- injects those findings into the model review prompt

So the verifier has moved from:

- "nice structural check"

to:

- "first-pass machine attention allocator"

That is a real product improvement.

### Structural analyzer reuse

Another important improvement is analyzer reuse with `gator-charter-draft.py`.

That reduces a classic governance failure mode:

- draft sees structure one way
- verify sees structure another way

Using the same analyzers makes the system much more coherent.

## Why This Matters to the Architect

If Gator is trying to keep code and charter layers aligned over time, it needs something more precise than vague intuition and cheaper than full human audit.

That is exactly the verifier's role.

It lets the Architect ask:

- where is charter drift probably accumulating?
- are there uncovered files?
- are we documenting functions at the right level?
- are some modules becoming more cross-cutting than their governance admits?

Without this tool, those questions require slower manual inspection.

## Relationship to Other Tools

### `gator-charter-lint.py`

Lint checks charter schema and formatting.

Verify checks charter plausibility against code structure.

Lint asks:

- "Is this a well-formed charter?"

Verify asks:

- "Does this charter still look true?"

### `gator-charter-draft.py`

Draft generates scaffolds.

Verify audits existing charters against live code.

They share analyzers, which is a major design strength.

### `enforcer-review.py`

Enforcer review is judgment-heavy.

Verify is mechanical.

Verify feeds enforcer review; it does not replace it.

## Known Limits

This tool is powerful, but it is still heuristic.

Important limits:

- it cannot infer architectural intent
- it may over-signal on some public functions that are intentionally undocumented
- it does not know whether a structural finding is important enough to block or escalate
- it depends on accurate `Covers:` and `File:` lines to be maximally useful

So a clean verify output is reassuring, but not sufficient.

And a noisy verify output is a cue for inspection, not an automatic verdict.

## Known Fragile Areas

### 1. Charter path topology

The command-post/source-repo world is more complicated than a normal governed repo.

If a tool reads the wrong charter surface, verify output becomes less trustworthy.

### 2. Charter quality

The verifier is only as good as the charter metadata it can parse.

Weak `Covers:` and missing `File:` references reduce precision.

### 3. Mechanical-vs-material confusion

It is easy to mistake verify findings for final truth.

They are not.

They are structured suspicion.

## High-Level Mental Model

If you want the most useful single-sentence model, it is this:

`gator-charter-verify.py` is the system's structural drift detector between code and charters.

It is the cheap mechanical pass that tells humans and enforcers where to look harder.

## Source of Truth Modules

Primary implementation:

- `src/gator_command/scripts/gator-charter-verify.py`

Supporting shared analysis:

- `src/gator_command/scripts/gator-charter-draft.py`

Current major downstream consumer:

- `.gator/scripts/enforcer-review.py`

## Where To Read Next

For ownership and function-level charter detail:

- `.gator/charters/scripts-repo-lifecycle.md`

For the review pipeline that consumes verify findings:

- `blueprints/commit-pipeline.md`
- `docs/enforcer-patterns.md`

For the higher-level governance model:

- `docs/governance-model.md`
