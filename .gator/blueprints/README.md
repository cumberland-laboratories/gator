# Blueprints

Per-feature flow maps — how features work end-to-end, referencing modules, functions, and charters.

Blueprints are optional. Create one when a feature or subsystem needs an architect-facing flow map.

## Structure

Each blueprint describes one feature:

```markdown
# Blueprint: <Feature Name>

## What It Does
[1-2 sentences]

## Flow
1. **<Module>** → `function_name()` — what happens
   → [charter-name](../charters/charter-name.md)

## Key Charters
[Charters involved in this flow]

## Invariants
[What must be true for this to work]
```

## Master Blueprint

Once you have several blueprints, create `system.md` — the architectural overview that links to individual feature blueprints.

See the [charters README](../charters/README.md) for the notation system used in function references.
