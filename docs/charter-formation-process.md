# Gator Charter Formation Process

This document describes the official process for creating a Gator charter set for a codebase that does not already have one.

The key distinction is:

- the **schema** defines what a valid charter looks like
- the **formation process** defines how a model should create that charter set responsibly

This matters because Gator's value does not come only from the final charter files.
It also comes from the inquiry pattern imposed on the model while those files are being created.

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

This is how the initial Gator map is formed.

## What the process is for

Use this process when:

- a fresh repo has no real charters
- a repo has only placeholder charter templates
- a subsystem was added and now needs charter coverage
- a legacy codebase is being brought into governed AI-assisted development

## Documents currently involved in bootstrap

Today the charter-bootstrap path is mainly driven by these documents:

1. `gator-start-up.md`
2. `reference-notes/identity-and-ownership.md`
3. `reference-notes/example-project.md`
4. `charters/README.md`
5. the relevant constitution once normal governed work begins

This document exists to make the process itself explicit and stable as a public reference, rather than leaving it distributed only across startup notes and examples.

## The formation process

## Step 1: Establish ownership context

Before forming a knowledge layer, determine the ownership model of the repo.

Questions:

- is this a solo repo or a team repo?
- who is the Architect?
- where does individual context belong?

This step matters because it shapes:

- `mission.md`
- tone and scope of shared knowledge
- what should and should not live in repo-native artifacts

Primary reference:

- `reference-notes/identity-and-ownership.md`

## Step 2: Scan for existing knowledge

Before inventing a map from scratch, inspect the repo for architectural knowledge that already exists.

Look for:

- top-level architecture or design docs
- ADRs
- module-level README files
- existing AI instruction files
- legacy knowledge systems

The goal is not to blindly copy these into Gator.
The goal is to identify what can seed:

- `mission.md`
- `roadmap.md`
- module charters
- cross-cutting charter
- threads for prior decisions

## Step 3: Understand the project

Before writing charters, the model should understand:

- what the project is
- what problem it solves
- what the current priorities are
- how the code is roughly organized

This step populates:

- `mission.md`
- `roadmap.md`

and gives the model enough context to interpret module boundaries intelligently.

## Step 4: Identify module boundaries

The model should walk the codebase and identify logical charter domains.

The unit is not "one file, one charter."
The unit is a **logical domain**.

Good boundaries include:

- a package or directory with a coherent responsibility
- a cluster of files that change together
- a subsystem with its own external dependencies or data model

This is the first major pattern-seeking step.

The model is being asked to determine:

- where the natural seams are
- which parts belong together
- which parts should not be merged into one charter

## Step 5: Form charter skeletons from code

For each boundary, the model creates an initial charter.

This stage is code-grounded:

- read the actual code
- enumerate important public functions/classes
- document what they do
- document reads/writes
- document callers and callees

The key rule:

**Do not invent. Extract from the code.**

If intent is unclear:

- ask the Architect
- or mark uncertainty explicitly

## Step 6: Add ownership and negative space

This is where the process becomes more than code extraction.

Every charter must include:

- `## Owns`
- `## Does Not Own`

`Does Not Own` is load-bearing.

This is one of the most important parts of the Gator process because it counteracts a model's default tendency to infer conventional architecture where the repo may deliberately differ.

The model is not just describing what exists.
It is identifying:

- which responsibilities belong here
- which responsibilities belong elsewhere
- which plausible assumptions must be denied explicitly

## Step 7: Identify tripwires and cross-cutting patterns

The model must then look for architectural truths that are not local to one function or one file.

Examples:

- multi-module data flows
- invariants spanning multiple code paths
- synchronized implementations
- "looks wrong but is intentional" patterns
- places where a model would otherwise normalize away a deliberate design choice

These belong in the cross-cutting charter and should be labeled clearly with:

- `TRIPWIRE`
- `Pattern`

This is the most fragile and distinctive part of the process.

It depends on precise instruction to the model to search for:

- non-obvious danger
- negative space
- multi-module invariants
- false-prior correction

## Step 8: Build the dispatch table

The model then writes `charters/INDEX.md`.

This turns the charter set into a navigable governance surface.

The dispatch table answers:

- if you are changing X, which charter(s) must you read first?

Without the dispatch table, charters remain present but harder to operationalize consistently.

## Step 9: Verify structurally

Once the initial charter set exists, verify:

- every major module is covered
- `INDEX.md` exists
- a cross-cutting charter exists
- obvious coverage gaps are addressed

This can be assisted mechanically, but the process is not tool-owned.

The model and Architect still decide:

- whether the charter set is materially good enough to begin governed coding

## Why this process is distinct

This is not just a documentation routine.

It is a constrained architectural inquiry process.

Compared to simpler repo-mapping approaches, the model is being asked to find:

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

That is why the process is more fragile and more valuable.

It depends on the model being instructed to look for the right kinds of patterns before it starts coding.

## Relationship to the charter schema

The formation process and the schema should stay separate.

Why:

- the schema should remain stable and testable
- the formation process is about inquiry, sequence, and behavioral discipline

In other words:

- [Gator Charter Schema v1](charter-schema-v1.md) says what a valid charter artifact looks like
- this document says how the initial charter set should be created

## Minimum public claim

The strongest public claim is not:

"Gator stores architecture notes."

It is:

"Gator requires the model to perform initial architectural trailblazing, then preserves the result as a maintained governance layer in the repo."

## Connections

→ [Gator Charter Schema v1](charter-schema-v1.md) — official artifact schema
→ [What Gator Requires From a Model](what-gator-requires-from-a-model.md) — behavioral assumptions behind the process
→ [Why Navigation Coding Feels Different](why-navigation-coding-feels-different.md) — why governed exploration feels different from prompt-only coding
→ `gator-start-up.md` — operational bootstrap instructions
→ `reference-notes/example-project.md` — density and tone reference
