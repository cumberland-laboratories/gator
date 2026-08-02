# Refactor Approach

This note describes how an AI agent should approach significant refactors under Gator.

The core idea: **do not "rewrite and hope."** Create a safe track, preserve behavior, extract behind stable seams, verify continuously, and keep the Architect involved in intent and boundary decisions.

## The Default Shape

For a non-trivial refactor, the agent should prefer this sequence:

1. Create a dedicated refactor branch from `dev`
2. Read the relevant charters and cross-cutting notes first
3. Confirm refactor intent and boundaries with the Architect
4. Identify stable seams where new modules can be introduced without changing public behavior
5. Extract new modules behind the existing call surface
6. Add or extend tests while behavior is still stable
7. Switch callers over only after the new path works
8. Remove old code only after parity is verified
9. Update charters to reflect the new ownership map

This is a **parallel-track refactor**, not a big-bang rewrite.

## Branch Discipline

Significant refactors should happen on a dedicated branch, not directly on `dev`.

Suggested names:

- `refactor/<area>`
- `feature/refactor-<area>`

Why:

- the refactor may take several commits before the code is clearer than it was
- the Architect needs a visible diff and a reversible checkpoint
- charter changes during a refactor can be substantial and should be reviewable as a set

If the work is high-risk, keep `main` as the known-good state, `dev` as the normal working branch, and the refactor branch as the isolated mutation surface.

## Charter-First Navigation

Before changing code, the agent should:

- read the module charters for the touched files
- read `cross-cutting.md` for repo-wide invariants and tripwires
- identify which functions are stable external surfaces versus internal implementation details
- identify what the Architect believes the module *should* own after the refactor

During refactors, charters serve four jobs:

- dependency map
- invariant checklist
- cutover checklist
- final ownership map

If the charters are missing or obviously stale, the right move is often to repair the map first, then refactor.

## Architect Checkpoints

Refactors need more Architect interaction than ordinary feature work.

The agent should explicitly confirm:

- the goal of the refactor
- what behavior must not change
- whether this is extraction, simplification, decomposition, or redesign
- whether naming and ownership should change
- whether compatibility shims are acceptable during transition

The agent should not silently reinterpret a refactor as a redesign.

Good checkpoint questions:

- "Is the goal better structure with behavior preserved, or are we also changing behavior?"
- "Should this module become thinner and delegate, or still own orchestration?"
- "Do you want a temporary adapter layer during migration?"

## Preferred Refactor Pattern

When possible, prefer:

1. leave the existing entry points in place
2. extract new logic into a new module
3. call the new module from the old path
4. verify behavior with tests
5. migrate callers gradually
6. delete the old implementation only after parity is established

This reduces blast radius and keeps rollback simple.

Examples:

- extract parsing logic out of a giant CLI script into `*_core.py`
- move file-system traversal into a helper module while keeping the old command entry point
- split a mixed "read + transform + render" function into separable pieces behind the same public API

## What To Avoid

Avoid these failure modes:

- rewriting large files wholesale without stable checkpoints
- changing public behavior and structure at the same time without Architect signoff
- moving ownership boundaries without updating charters
- deleting old code before the new path is tested
- introducing new abstractions that are not yet called by the existing program
- mixing refactor work with unrelated feature additions

The smell is: **the diff is large, the behavior changed, the ownership moved, and there is no parity proof.**

## Tests During Refactor

Tests are part of the extraction path, not a cleanup step afterward.

Preferred order:

1. identify current behavior
2. capture it with tests where practical
3. extract new module
4. route old entry point through new module
5. extend tests for the new boundary
6. remove legacy path only after green verification

Where full automated coverage is not available, use:

- targeted script invocations
- golden-file comparisons
- fixture-based behavior checks
- before/after command output comparison

For AI-assisted refactors, "works on inspection" is not enough.

## Charter Updates During Refactor

Refactors often create temporary asymmetry between code and charters. The agent should keep the map usable throughout the transition.

Preferred approach:

- update charters incrementally as ownership moves
- note temporary adapters explicitly
- update `Covers`, caller/callee arrows, and tripwires as soon as they change
- remove obsolete charter entries when the old code is actually gone

If a temporary shim exists, the charter should say so plainly.

## A Good Refactor Outcome

A good Gator refactor leaves:

- smaller modules with clearer ownership
- stable entry points or an explicit migration path
- tests that prove parity or intended change
- charters that match the new structure
- a branch diff the Architect can review coherently

The refactor is not complete when the code "looks cleaner." It is complete when the **structure, tests, and charters agree**.
