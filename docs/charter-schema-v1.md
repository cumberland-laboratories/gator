# Gator Charter Schema v1

**Version**: charter-schema-v1
**Status**: Official public schema
**Source**: Codified from de facto patterns across gator-command and governed repos (2026-06-03), published as the reference schema for external use

This document defines the official structural schema for Gator charter files.

It is intended to be stable enough for:

- external tool builders
- research comparisons
- validator implementations
- charter generation experiments
- cross-vendor and cross-repo testing

The validator (`gator-charter-lint.py`) checks files against this schema.

## Scope

This schema covers the shape of charter artifacts:

- charter file structure
- function-entry structure
- `INDEX.md` dispatch-table structure
- cross-cutting charter minimum structure

It does **not** define:

- how a model should discover module boundaries
- how tripwires should be found
- how charter content should be bootstrapped from a fresh codebase

Those belong to the charter-formation process, documented separately in:

- [Gator Charter Formation Process](charter-formation-process.md)

## Design Principles

- **Descriptive, not prescriptive**: the schema captures the patterns that already exist across working charters
- **Structural, not qualitative**: checks that sections exist and entries are well-formed, not whether content is good
- **Flexible notation**: accepts both ASCII (`<-`/`->`) and Unicode (`←`/`→`) arrows, multiple access pattern styles
- **Skeleton-friendly**: a charter with no function entries is valid — the ownership sections are the minimum

---

## Charter File Schema

Charter files live in `.gator/charters/` or `gator-command/charters/`. Excluded from validation: `_template.md`, `README.md`.

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
| `**Covers**:` | Error | Exempt for cross-cutting charters (they cover patterns, not files) |
| `## Owns` | Error | Must exist |
| `## Does Not Own` | Error | Must exist |
| `---` separator | Error | At least one, before any function entries |
| `## Before Changing This Module` | Warn | Recommended when function entries exist — not blocking because skeleton charters are valid |
| `## Connections` | Warn | Recommended when function entries exist |

### Function Entry Schema

Each function entry starts with `### ` within a charter file.

| Element | Enforcement | Format |
|---------|-------------|--------|
| Heading | Error | `### name(args)` or `### script-name.sh` (free-form after `### `). When the same function name exists in multiple covered files (e.g. bash and Python implementations), disambiguate with `### name(args) [filename.ext]` — e.g. `### detect_scenario(target) [gatorize-lib.sh]` vs `### detect_scenario(target)` with `File: gatorize.py`. |
| File line | Warn | `File:` line recommended (especially for multi-file charters), not blocking for single-file or bash charters where the covered file is obvious |
| Description | Warn | At least one non-annotation line after heading |
| Access patterns | No | `@reads:`, `@writes:`, `Models:`, `Filesystem:`, `Session R:`, `Session W:` |
| Callers | No | `←` or `<-` prefix |
| Callees | No | `→` or `->` prefix |
| Tripwires | No | `!` prefix (may span continuation lines) |

---

## INDEX.md Schema

Every `.gator/charters/` directory should have an `INDEX.md`.

| Element | Required | Format |
|---------|----------|--------|
| Title | Yes | `# Charter Index` |
| Cross-cutting pointer | No | "Always read first" line pointing to cross-cutting.md |
| Dispatch table | Yes | Markdown table with code-path → charter mapping |

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
|----------|---------|-----------------|
| `error` | Schema violation — required element missing or malformed | Causes exit 1 |
| `warn` | Suspicious but not broken — missing optional-but-recommended element | No effect on exit code |
| `info` | Suggestion — entry is sparse but valid | No effect on exit code |

## Connections

→ [Charter Formation Process](charter-formation-process.md) — how a fresh charter set is actually created
→ [Charter Philosophy](../gator-command/charters/README.md) — why charters exist, the notation system
→ [Charter Template](../gator-command/charters/_template.md) — blank template
→ [`gator-charter-lint.py`](../gator-command/scripts/gator-charter-lint.py) — validator implementation
