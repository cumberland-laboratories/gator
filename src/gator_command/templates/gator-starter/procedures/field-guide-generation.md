# Field Guide Generation

**When to use**: When ≥2 charters reference the same language and the Architect wants condensed pattern reference material. Field guides are optional — the system never prompts for them.

A field guide has two audiences in two files per language: a **pattern sheet** (`{slug}-patterns.md`, concise dispatch table for the agent) and a **tutorial** (`{slug}-tutorial.md`, real snippets with rationale for the Architect). Separate files so the agent loads only the condensed sheet; the Architect reads the tutorial at their own pace.

## Step 0 — Maturity Gate

Count charters in `charters/` (skip `_template.md`, `README.md`, `INDEX.md`). For each charter, read the `Covers` line and `File:` lines. Map file extensions to language slugs:

| Extension | Slug |
|-----------|------|
| `.py` | python |
| `.sh` | bash |
| `.js` | javascript |
| `.ts` | typescript |
| `.go` | go |
| `.rs` | rust |
| `.gd` | gdscript |

A language qualifies when **all three** conditions are met:
- ≥2 charters reference files with that extension
- ≥4 source files with that extension across those charters
- ≥8 extractable patterns (estimated — confirm after Step 3)

If no language qualifies, stop. Tell the Architect: "This repo doesn't have enough chartered code to generate a useful field guide yet. Field guides work best when charters cover multiple modules in the same language."

## Step 1 — Inventory Languages from Charters

Read all charter files. For each, extract:
- The `Covers:` line (lists primary files)
- Lines starting with `File:` inside function entries
- `@reads:` and `@writes:` paths that reference source files

Build a map: `{language_slug: [{charter_name, [files]}]}`

Example:
```
python:
  - boot-version: [gator-init.py, gator-update.py, gator-version.py]
  - fleet-intelligence: [gator-fleet-report.py, gator-drift.py, gator-audit.py]
  - gator-core: [gator_core.py]
  - installer: [gatorize.py]
```

## Step 2 — Extract Patterns from Charters

For each qualifying language, scan its charters for:

| Charter element | Pattern type |
|----------------|--------------|
| `TRIPWIRE` sections | Constraint (highest priority) |
| `!` lines in function entries | Gotcha / non-obvious behavior |
| `@reads:` / `@writes:` tags | Data flow pattern |
| `←` / `→` cross-references | Dependency pattern |
| "Before Changing" invariants | Guard / pre-condition |
| "Does Not Own" boundaries | Scope boundary |

Record each pattern with: name, source charter, affected files, 1-sentence description.

## Step 3 — Extract Patterns from Code

Read the actual source files identified in Step 1. Look for:

- **Recurring idioms** (3+ uses): Same code shape appearing in multiple functions or files. Name the shape.
- **Structural conventions**: How files are organized (section headers, function ordering, import structure).
- **Guard patterns**: How errors, missing files, and edge cases are handled. Note the common try/except or if/return shapes.
- **Naming conventions**: Variable naming, function naming, constant naming patterns.
- **Error handling**: What gets caught, what gets returned on failure, how errors propagate.

For each pattern, note: which files use it, approximate frequency, whether it connects to a charter pattern from Step 2.

## Step 4 — Merge and Rank

Combine charter patterns (Step 2) and code patterns (Step 3). Deduplicate — if the same pattern appears in both, merge into one entry with richer context.

Rank by: `frequency × importance`

- TRIPWIRE patterns get 3× boost (breaking these has fleet-wide consequences)
- `!` gotcha patterns get 2× boost (these cause subtle bugs)
- Patterns appearing in 3+ files get 1.5× boost
- Patterns unique to one file get 0.5× weight (may be local, not language-wide)

Cut to **8–20 patterns**. If you have more than 20, you're documenting implementation details, not patterns. If fewer than 8, the language may not qualify after all — revisit the maturity gate.

## Step 5 — Write Agent Pattern Sheet

A separate file: `.gator/field-guides/{slug}-patterns.md`. Target: **under 80 lines**. The agent loads only this file alongside charters — it must be self-contained and concise.

Format for each entry:

```markdown
### Pattern Name
Files: file1.py, file2.py
1–3 line description of when and how to apply this pattern.
! Optional tripwire note — only if violating this pattern has non-obvious consequences.
```

Rules:
- No code snippets in the pattern sheet (those go in the tutorial)
- Every file reference must be a real file in the repo
- Description answers: "When I encounter [situation], I should [action]"
- Group related patterns (e.g., all error-handling patterns together)
- Describe observed reality, not aspirational norms. If a pattern is followed by most scripts but not all, say which scripts follow it.

## Step 6 — Write Architect Tutorial

A separate file: `.gator/field-guides/{slug}-tutorial.md`. Target: **under 300 lines** (~5 pages). Cross-references the pattern sheet via frontmatter `patterns:` field.

For each pattern from the pattern sheet (or a curated subset of the most important):

```markdown
### Pattern Name

**Charter connection**: [charter name] — [specific section or tripwire]

[Real code snippet from the repo, 3–10 lines, showing the pattern in use]

**Why it matters**: 1 paragraph explaining what goes wrong if you violate this pattern
or don't recognize it when reading code.

**What to watch for**: 1 sentence — the signal that this pattern is relevant to
what you're currently reading or writing.
```

Rules:
- Every snippet must be copied from actual repo code (not invented)
- Cite the source file for each snippet
- Keep "why it matters" grounded in this repo's specific history or architecture, not generic advice
- The tutorial reads like a colleague walking you through the codebase

## Step 7 — Assemble and Validate

Write two files per language in `.gator/field-guides/`:

**Pattern sheet** (`{slug}-patterns.md`) frontmatter:
```yaml
---
generated: YYYY-MM-DD
generator: field-guide-gen-v1
type: agent-patterns
language: {slug}
source-charters: [{charter1}, {charter2}, ...]
source-file-count: {N}
pattern-count: {N}
tutorial: {slug}-tutorial.md
---
```

**Tutorial** (`{slug}-tutorial.md`) frontmatter:
```yaml
---
generated: YYYY-MM-DD
generator: field-guide-gen-v1
type: architect-tutorial
language: {slug}
source-charters: [{charter1}, {charter2}, ...]
patterns: {slug}-patterns.md
---
```

**Validation checklist**:
- [ ] Every file reference in "Files:" lines resolves to a real file
- [ ] Every charter reference in "Charter connection:" resolves to a real charter
- [ ] Pattern count in frontmatter matches actual pattern count
- [ ] Pattern sheet is under 80 lines
- [ ] Tutorial is under 300 lines
- [ ] No invented code snippets — every snippet traces to a source file
- [ ] Pattern sheet and tutorial cross-reference each other in frontmatter

## Reference

→ [Constitution](../constitution.md) — field-guides/ in the file purposes table
→ [Charter Format](../charters/README.md) — the notation these patterns reference
→ [Concierge Responses](../reference-notes/concierge-responses.md) — when to surface field guides to the Architect
