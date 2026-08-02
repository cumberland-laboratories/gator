# Gator Charter Formation Process

This document describes the official process for creating the first Gator charter set for a codebase.

The key distinction is:

- the **schema** defines what a valid charter looks like
- the **formation process** defines how a model should create that charter set responsibly

This matters because Gator's value comes not only from the final charter files, but from the inquiry process imposed on the model while those files are being created.

## Purpose

The process exists to force architectural inquiry before coding acceleration.

The model is not supposed to:

- skim a few files
- invent a plausible architecture summary
- start coding from generic priors

The model is supposed to:

- establish ownership context
- scan for existing knowledge
- identify real module boundaries
- extract ownership and negative space from the code
- identify cross-cutting invariants and tripwires
- compress those findings into a small, usable map

## Documents involved in bootstrap

The local bootstrap path is mainly driven by:

1. `gator-start-up.md`
2. `reference-notes/identity-and-ownership.md`
3. `reference-notes/example-project.md`
4. `charters/README.md`
5. the repo constitution once normal governed work begins

This document exists to make the process itself explicit and stable as a local reference.

## The formation process

## Step 1: Establish ownership context

Before forming a knowledge layer, determine:

- is this a solo repo or a team repo?
- who is the Architect?
- where does individual context belong?

Primary reference:

- `reference-notes/identity-and-ownership.md`

## Step 2: Scan for existing knowledge

Before inventing a map from scratch, inspect the repo for architectural knowledge that already exists.

Look for:

- top-level architecture or design docs
- ADRs
- module README files
- existing AI instruction files
- legacy knowledge systems

The goal is to identify what can seed:

- `mission.md`
- `roadmap.md`
- module charters
- cross-cutting charter
- threads for prior decisions

## Step 3: Understand the project

Before writing charters, understand:

- what the project is
- what problem it solves
- what the current priorities are
- how the code is roughly organized

This step populates:

- `mission.md`
- `roadmap.md`

## Step 4: Identify module boundaries

Identify logical charter domains.

The unit is not "one file, one charter."
The unit is a **logical domain**.

Good boundaries include:

- a package or directory with a coherent responsibility
- a cluster of files that change together
- a subsystem with its own external dependencies or data model

## Step 5: Form charter skeletons from code

For each boundary:

- read the actual code
- enumerate important public functions/classes
- document what they do
- document reads/writes
- document callers and callees

Rule:

**Do not invent. Extract from the code.**

If intent is unclear:

- ask the Architect
- or mark uncertainty explicitly

## Step 6: Add ownership and negative space

Every charter must include:

- `## Owns`
- `## Does Not Own`

`Does Not Own` is load-bearing.

The model is not just describing what exists.
It is identifying:

- which responsibilities belong here
- which responsibilities belong elsewhere
- which plausible assumptions must be denied explicitly

## Step 7: Identify tripwires and cross-cutting patterns

The model must look for architectural truths that are not local to one function or one file.

Examples:

- multi-module data flows
- invariants spanning multiple code paths
- synchronized implementations
- "looks wrong but is intentional" patterns
- places where a model would otherwise normalize away a deliberate design choice

These belong in the cross-cutting charter and should be labeled clearly with:

- `TRIPWIRE`
- `Pattern`

## Step 8: Build the dispatch table

Write `charters/INDEX.md`.

This turns the charter set into a navigable governance surface.

The dispatch table answers:

- if you are changing X, which charter(s) must you read first?

## Step 9: Verify structurally

Once the initial charter set exists, verify:

- every major module is covered
- `INDEX.md` exists
- a cross-cutting charter exists
- obvious coverage gaps are addressed

The process is not tool-owned.
The model and Architect still decide whether the charter set is materially good enough to begin governed coding.

## Why this process is distinct

This is not just a documentation routine.

It is a constrained architectural inquiry process.

The model is being asked to find:

- boundaries
- ownership
- negative space
- invariants
- tripwires

not merely:

- files
- classes
- functions
- signatures

## Relationship to the charter schema

The formation process and the schema should stay separate.

- [Gator Charter Schema v1](charter-schema-v1.md) says what a valid charter artifact looks like
- this document says how the initial charter set should be created

## Connections

→ [Gator Charter Schema v1](charter-schema-v1.md) — official artifact schema
→ [`../reference-notes/example-project.md`](../reference-notes/example-project.md) — density and tone reference
→ [`../reference-notes/identity-and-ownership.md`](../reference-notes/identity-and-ownership.md) — ownership-context bootstrap step
→ [`../charters/README.md`](../charters/README.md) — notation, philosophy, and anti-patterns
