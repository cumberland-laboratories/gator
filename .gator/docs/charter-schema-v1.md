# Gator Charter Schema v1

**Version**: charter-schema-v1
**Status**: Official local schema
**Source**: Codified from working Gator charters and shipped as a standalone repo reference

This document defines the official structural schema for Gator charter files inside a governed repo.

It is intended to be stable enough for:

- local validator implementations
- cross-model consistency checks
- external experiments using Gator charters
- research or tests comparing charter quality across repos

This schema describes what a valid charter artifact looks like.

## Scope

This schema covers:

- charter file structure
- function-entry structure
- `INDEX.md` dispatch-table structure
- cross-cutting charter minimum structure

It does **not** define:

- how a model should discover module boundaries
- how tripwires should be found
- how the first charter set should be formed

Those belong to the charter-formation process:

- [Gator Charter Formation Process](charter-formation-process.md)

## Design Principles

- **Structural, not qualitative**: this schema checks shape and minimum expectations, not whether a charter is insightful
- **Stable enough for tooling**: external validators and experiments should be able to rely on the basic format
- **Flexible notation**: accepts both ASCII (`<-`/`->`) and Unicode (`←`/`→`) arrows
- **Skeleton-friendly**: a thin but structurally valid charter is still a charter

---

## Charter File Schema

Charter files live in `.gator/charters/`. Excluded from validation: `_template.md`, `README.md`.

### Required Structure

```
# Charter: [Name]                          ← ERROR if missing

**Covers**: `path/to/files`                ← ERROR if missing (exempt for cross-cutting)

## Owns                                    ← ERROR if missing

[What this module is responsible for]

## Does Not Own                            ← ERROR if missing

[What belongs elsewhere]

---                                        ← ERROR if missing when function entries exist

### function_name(args)                    ← OPTIONAL: zero or more function entries
File: path/to/file.py                      ← WARN if missing (recommended, not blocking)
[Description]                              ← WARN if missing
@reads: ...                                ← OPTIONAL
@writes: ...                               ← OPTIONAL
← [callers]                                ← OPTIONAL (also accepts <-)
→ [callees]                                ← OPTIONAL (also accepts ->)
! [tripwire]                               ← OPTIONAL

---

## Before Changing This Module             ← WARN if missing when functions exist

[Institutional knowledge]

## Connections                             ← WARN if missing when functions exist

→ [Other Charter](other.md) — why
```

### Section Rules

| Section | Enforcement | Notes |
|---------|-------------|-------|
| `# Charter: [Name]` | Error | First line of the file |
| `**Covers**:` | Error | Exempt for cross-cutting charters |
| `## Owns` | Error | Must exist |
| `## Does Not Own` | Error | Must exist |
| `---` separator | Error | At least one, before any function entries |
| `## Before Changing This Module` | Warn | Recommended when function entries exist |
| `## Connections` | Warn | Recommended when function entries exist |

### Function Entry Schema

Each function entry starts with `### ` within a charter file.

| Element | Enforcement | Format |
|---------|-------------|--------|
| Heading | Error | `### name(args)` or free-form after `### `. Disambiguate duplicate names with `[filename.ext]` when needed. |
| File line | Warn | `File:` line recommended |
| Description | Warn | At least one non-annotation line after heading |
| Access patterns | No | `@reads:`, `@writes:`, `Models:`, `Filesystem:`, `Session R:`, `Session W:` |
| Callers | No | `←` or `<-` prefix |
| Callees | No | `→` or `->` prefix |
| Tripwires | No | `!` prefix |

---

## INDEX.md Schema

Every `.gator/charters/` directory should have an `INDEX.md`.

| Element | Required | Format |
|---------|----------|--------|
| Title | Yes | `# Charter Index` |
| Cross-cutting pointer | No | "Always read first" line pointing to `cross-cutting.md` |
| Dispatch table | Yes | Markdown table mapping code paths to charter files |

---

## cross-cutting.md Schema

If a cross-cutting charter exists, it should contain:

| Element | Required | Format |
|---------|----------|--------|
| At least one `TRIPWIRE` or `Pattern` section | Yes | `## TRIPWIRE:` or `## Pattern:` heading |
| `## Owns` | Yes | Multi-module invariants scope |
| `## Does Not Own` | Yes | Module-specific logic exclusion |

---

## Severity Model

The validator uses three severity levels:

| Severity | Meaning | Exit code effect |
|----------|---------|------------------|
| `error` | Schema violation — required element missing or malformed | Causes exit 1 |
| `warn` | Suspicious but not broken — optional-but-recommended element missing | No effect on exit code |
| `info` | Suggestion — entry is sparse but valid | No effect on exit code |

## Connections

→ [Gator Charter Formation Process](charter-formation-process.md) — how the initial charter set is created
→ [`../charters/README.md`](../charters/README.md) — notation, philosophy, anti-patterns
→ [`../charters/_template.md`](../charters/_template.md) — blank template
