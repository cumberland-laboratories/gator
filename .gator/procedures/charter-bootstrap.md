# Procedure: Charter Bootstrap

**When to use**: When a repo has missing charters, weak charters, or a newly added subsystem that does not yet have a trustworthy governance substrate.

This procedure exists because Gator is now stronger at enforcement than at initialization. Once charters exist, the hook and enforcer can keep them honest. The weak point is the beginning.

## Goal

Create a minimum viable charter substrate that is strong enough for governed coding to begin.

This procedure does **not** require perfect charters before work starts.

It does require:

- a resolved authoritative charter surface
- structural scaffolds
- semantic enrichment
- at least one verify pass
- Architect review of the resulting evidence

## Product Principle

Use a strict machine/agent split:

- **Machine work**: discovery, scaffold generation, structural verification
- **Agent work**: `Owns`, `Does Not Own`, tripwires, rationale, semantic boundaries

Do not let the agent freestyle the entire bootstrap process by grep.

## Phase 0: Resolve Charter Surface

Before doing anything else, resolve the authoritative charter surface for the repo.

Canonical source:

- `gator_core.resolve_charter_surface(repo_root)`

Expected modes:

- `source-command-post` -> `.gator/charters/`
- `governed-repo` -> `.gator/charters/`

The agent must not guess this topology manually.

## Phase 1: Discover

Determine:

- which tracked source files need charter coverage
- whether charters already exist
- whether `INDEX.md` exists and is usable
- whether the cross-cutting charter exists

Primary tools:

- `gator-charter-draft.py` discovery path
- existing charter inventory
- `INDEX.md`

Questions to answer:

- what source files are in scope?
- which files are already covered?
- which files are uncovered?
- is this a fresh bootstrap or a repair/re-charter?

## Phase 2: Scaffold

Run the mechanical scaffold generator.

Primary tool:

- `gator-charter-draft.py`

Expected output:

- charter filenames
- `Covers:` lines
- function/class inventories
- imports
- basic structure for later enrichment

Important boundary:

This phase creates substrate.

It does not complete charter meaning.

## Phase 3: Agent Enrichment

The agent fills in the semantic parts the machine cannot be trusted to invent.

This includes:

- `## Owns`
- `## Does Not Own`
- tripwires
- important cross-references
- rationale
- non-obvious boundaries

The agent should enrich the scaffold, not rebuild the mechanical structure from scratch.

## Phase 4: Structural Verify

Run:

- `gator-charter-verify.py`

This phase is mandatory.

Use it to gather evidence about:

- `coverage-gap`
- `function-gap`
- `complexity-mismatch`
- `stale-structure`
- `cross-cutting-suspect`

Treat verify as a structural gate and evidence source.

Do **not** treat it as an automatic repair engine.

## Phase 5: Repair and Re-Verify

Use the verify output to decide what needs repair.

Typical repair work:

- add missing `Covers:` mappings
- fill meaningful function gaps
- improve thin charters
- add missing cross-cutting treatment
- update `INDEX.md`
- add missing `File:` lines on important entries

Important rule:

The tool produces evidence. The agent and Architect decide which findings are materially important before proceeding.

## Phase 6: Architect Readiness Review

The Architect makes the final call on whether the repo is ready for substantial governed coding.

Do not collapse this into a tool-owned boolean.

The right outputs are:

- evidence
- finding counts
- blocking concerns
- advisory concerns
- a clear statement of what still looks weak

The Architect decides whether the governance substrate is sufficient.

## Minimum Viable Charter Substrate

This is the threshold the Architect should usually look for before green-lighting coding.

### Required

- every relevant source file is covered by some charter
- the authoritative charter surface exists
- `INDEX.md` exists for that surface
- the cross-cutting charter exists
- no major `coverage-gap` findings remain

### Strongly Recommended

- major module charters have real `Owns` / `Does Not Own` sections
- key public entry points are represented
- obvious cross-cutting concerns are acknowledged
- `File:` lines exist on important function entries

### Not Required

- perfect prose
- exhaustive tripwires
- zero warnings of any kind

## Output Expectations

At the end of bootstrap, the repo should have:

- real charters in the authoritative surface
- an `INDEX.md`
- a cross-cutting charter
- recent verify output the Architect can inspect

If possible, also produce a short Architect-facing summary:

- files discovered
- charters created or updated
- major verify findings
- open risks or weak spots

## What This Procedure Does NOT Do

- It does not promise perfect charters.
- It does not let a tool declare "ready for coding" without Architect judgment.
- It does not replace the enforcer.
- It does not replace future dashboard visibility.

## Recommended Sequence in Practice

1. Resolve charter surface.
2. Discover uncovered or weak areas.
3. Run scaffold generation.
4. Enrich charters semantically.
5. Run charter verify.
6. Repair important issues.
7. Re-run verify.
8. Present evidence to the Architect.
9. Begin governed coding only after Architect review.

## Relationship to Other Systems

- Charter bootstrap creates the substrate the pre-commit hook later enforces.
- `gator-charter-verify.py` is the main structural evidence source in this procedure.
- The enforcer can later consume the same verify findings as structural priors.
- A future dashboard surface should expose charter health so the Architect can inspect the repo without rerunning grep-style discovery.

## Connections

-> [charter-lookup.md](charter-lookup.md) - what to read before modifying code once charters exist
-> [../../.gator/procedures/enforcer-review.md](../../.gator/procedures/enforcer-review.md) - read-only enforcer flow and Architect review boundary
-> [../artifacts/2026-06-09-charter-bootstrap-pipeline-v1.md](../artifacts/2026-06-09-charter-bootstrap-pipeline-v1.md) - planning rationale behind this procedure
