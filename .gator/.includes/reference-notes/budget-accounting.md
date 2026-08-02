# Reference Note: Budget Accounting

## What Counts Toward the 400-Line Budget

The always-loaded content budget includes exactly:

- `identity.md` — full file
- `inbox.md` — full file
- `active-threads/*.md` — all files **except** `_TEMPLATE.md`
- `patterns/*.md` (rhythms) — all files **except** `README.md`

## What Is Excluded

- `constitution.md` — always loaded but budget-exempt. Governance infrastructure, not knowledge content.
- `_TEMPLATE.md` — structural template, not loaded into conversation context.
- `patterns/README.md` — directory description, not loaded.
- `threads/` — not always loaded.
- `artifacts/` — not always loaded.
- `procedures/` — loaded on demand.
- `reference-notes/` — loaded on demand.

## Counting Rules

- All lines count, including blank lines and frontmatter.
- The `memex-lint.sh` script is the authoritative budget calculator.
- "Under budget" means the lint script reports 400 or fewer.
