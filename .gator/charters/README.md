# Charters

Charters are the compact architectural map of this repository. They explain ownership, boundaries, state access, dependency direction, and non-obvious invariants without making a reader load the implementation.

## Reading Route

1. Read [`scripts-cross-cutting.md`](scripts-cross-cutting.md) for repository-wide contracts.
2. Use [`INDEX.md`](INDEX.md) to select only the charter rows matching the files you will change.
3. Follow a charter's `## Connections` links only when the change crosses that boundary.

`INDEX.md` is the single authoritative code-path-to-charter map. Do not duplicate that table elsewhere.

## Required Shape

Every module charter uses this order:

```markdown
# Charter: Domain

**Covers**: `path/or/glob/**`

## Owns
[Responsibilities and durable contracts.]

## Does Not Own
[Adjacent responsibilities that belong elsewhere.]

### function_name(args)
File: path/to/file.py
[One-line behavior and important state access.]
<- callers
-> callees
! non-obvious invariant

## Before Changing This Module
[Short checklist of contracts to preserve.]

## Connections
-> Other Charter - link the real neighboring charter and explain the boundary
```

Use function or class names, never line numbers. Group tightly related helpers in one entry when they share the same boundary and invariant.

## Notation

| Marker | Meaning |
|---|---|
| `File:` | Owning implementation path |
| `Filesystem:` | Important file reads or writes |
| `<-` | Callers or entry points |
| `->` | Dependencies or callees |
| `!` | A tripwire: behavior that is easy to break or "improve" incorrectly |
| `(R)`, `(W)`, `(RW)` | Read, write, or read/write access |

## Scope Rules

A charter is an architectural map, not a changelog, test report, implementation plan, or exhaustive API reference.

Keep:

- Current ownership and negative-space boundaries.
- Public seams and high-blast-radius helpers.
- File/state access that predicts side effects.
- Cross-module contracts and security boundaries.
- The smallest useful set of regression-test names when they uniquely identify a tripwire.

Move or omit:

- Release chronology, review-round history, and resolved findings.
- Long test inventories and pass counts.
- Superseded behavior and deleted-function narratives.
- Detailed algorithms that are clear from the code.
- Design rationale already preserved in an artifact, ADR, issue, or Git history.

## Size and Modularity

Aim for **80-220 lines** and one coherent code domain per charter. Split a charter when any of these are true:

- It exceeds roughly 250 lines or 30 KB.
- Its `**Covers**` field spans independently changeable subsystems.
- A reader routinely needs only one part of it.
- `## Owns` needs more than about ten bullets to explain the domain.
- Historical narration is longer than the current contract.

The always-read cross-cutting charter has a stricter bar: include only invariants that cross two or more domain boundaries. Domain-local security, UI, release, or data rules belong in their domain charter and are linked from cross-cutting only when necessary.

## Maintenance

Update the affected charter in the same operation as a code change when ownership, behavior, state access, dependencies, or tripwires change. Routine internal refactoring that preserves those contracts does not need prose churn.

If code and charter disagree, stop and resolve the drift using Git history and the [charter alignment procedure](../.includes/procedures/charter-alignment.md).

Validate the set with:

```text
python src/gator_command/scripts/gator-charter-lint.py --charters-dir .gator/charters
python src/gator_command/scripts/gator-charter-verify.py --path .
```

The linter checks charter shape. The verifier reports coverage, stale structure, and likely gaps; its informational findings require judgment rather than automatic expansion.
