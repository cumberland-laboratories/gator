# Procedure: Artifact Freshness and Current Truth

**When to use**: Any time an older artifact, report, or dated planning note appears to conflict with the current state of the system.

## Purpose

Clarify which layers in Gator are allowed to become historically stale, and which layers are expected to remain current.

This prevents two common failure modes:

- rewriting historical artifacts so aggressively that the design record becomes useless
- treating old artifacts as if they were the current contract

## Core Rule

Artifacts are allowed to age.

Current truth must live somewhere else.

## Layer Rules

### Artifacts

Location:

- `.gator/artifacts/`

Role:

- dated planning records
- historical design snapshots
- deep analysis
- point-in-time thinking

Expectation:

- may become partially obsolete
- should usually remain intact as historical records

Do not treat artifacts as the primary source of current operational truth.

### Procedures

Location:

- `.gator/procedures/`

Role:

- canonical workflows
- current operational rules

Expectation:

- should stay current

If the workflow changed, update the procedure rather than "fixing" old artifacts.

### Blueprints

Location:

- `.gator/blueprints/` (source repo) or `.gator/blueprints/` (governed repos)

Role:

- current Architect-readable explanation of how major subsystems work

Expectation:

- should stay current

Blueprints are the human-readable current truth layer for subsystem behavior.

### Charters

Location:

- `.gator/charters/`
- `.gator/charters/`

Role:

- current ownership, invariants, boundaries, tripwires

Expectation:

- should stay current

Charters are the live module contract, not historical notes.

### Reports

Location:

- `docs/reports/`

Role:

- dated audits and generated snapshots

Expectation:

- may age
- should be read as point-in-time evidence

## What To Do When an Artifact Ages

If an artifact is no longer directionally current:

1. Do not rewrite it just to erase the drift.
2. Identify the current-truth layer that should now carry the active contract:
   - procedure
   - blueprint
   - charter
   - sometimes roadmap or issue thread
3. Update that live layer.
4. If helpful, add a short note or cross-reference from the artifact to the current document.

## Acceptable Artifact Annotation

If an older artifact is likely to mislead future readers, add a light annotation rather than rewriting its historical content.

Good examples:

- "Historical planning snapshot; see current procedure X"
- "Superseded direction; see current blueprint Y"
- "This artifact reflects the design state as of YYYY-MM-DD"

The goal is orientation, not revisionism.

## When To Update the Artifact Itself

Update an artifact only when:

- metadata is missing or broken
- links are broken enough to make it unusable
- a small annotation would prevent serious confusion

Do not convert old artifacts into living docs by continuously rewriting them.

## Decision Rule

When a file appears stale, ask:

"Is this file supposed to be a snapshot, or is it supposed to be today's truth?"

If snapshot:

- preserve it
- maybe annotate it

If current truth:

- update it

## Relationship to Other Layers

- Artifacts preserve how thinking evolved.
- Procedures define what to do now.
- Blueprints explain how the system works now.
- Charters define module truth now.

That separation is intentional and should be preserved.

## Connections

-> [knowledge-capture.md](knowledge-capture.md) - where deep analysis and project knowledge should go
-> [charter-bootstrap.md](charter-bootstrap.md) - example of a procedure that supersedes older planning artifacts
-> [blueprints/README.md](../blueprints/README.md) - current subsystem explanation layer
