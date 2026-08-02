# Gator Start-Up — Bootstrap Procedure

**When to use**: First session on a fresh project, OR when `charters/` is empty or contains only templates.

This procedure creates the initial knowledge layer. After this, the normal loop takes over (constitution.md governs ongoing work).

## Before You Start

Read the worked example in [`reference-notes/example-project.md`](reference-notes/example-project.md). It shows what a fully populated Gator looks like for a simple Python project — mission, roadmap, charters, threads, the whole thing. Study the charter format and density. That's what you're building toward.

For the formal public references behind this bootstrap flow, also read:

- [`docs/charter-schema-v1.md`](docs/charter-schema-v1.md) — the official charter artifact schema
- [`docs/charter-formation-process.md`](docs/charter-formation-process.md) — the official process for creating the first charter set

## Step 1: Establish Ownership Context

Before anything else, read [`reference-notes/identity-and-ownership.md`](reference-notes/identity-and-ownership.md). Then determine: is this a solo repo or a team repo? This shapes how you write `mission.md` and everything downstream. Don't skip this — getting identity wrong early creates drag that compounds.

## Step 2: Scan for Existing Knowledge

Before building the knowledge layer from scratch, look for existing documentation or structure in the repo that could be migrated into `.gator/`. Many repos already have some form of architectural knowledge — just not in Gator's format.

**Scan for:**
- `ARCHITECTURE.md`, `DESIGN.md`, `CONTRIBUTING.md`, or similar top-level docs
- `docs/` folders with architecture, decisions, or design documents
- ADR (Architecture Decision Records) directories (`docs/decisions/`, `docs/adr/`, `adr/`)
- Existing charter-like files (`docs/charters/`, `docs/modules/`)
- Homegrown knowledge folders (`memex/`, `.memex/`, `docs/knowledge/`)
- Inline module documentation (`README.md` files inside package directories)
- `.cursorrules`, `.github/copilot-instructions.md`, or other AI instruction files

**If you find existing knowledge**, tell the Architect what you found and offer to migrate:

- Architecture docs → seed `mission.md`, charters, and cross-cutting charter
- ADRs → convert to threads (one thread per decision, preserving rationale)
- Module READMEs → seed the charter for that module's "Owns" and boundaries
- Existing AI instructions → review for content that should move into the constitution or reference notes (and keep the original for model-specific config)

Don't migrate silently. Show the Architect what you found, suggest where it maps, and ask before copying. Some of it may be outdated or intentionally separate.

## Step 3: Understand the Project

Ask the Architect (or read existing docs, including anything found in Step 2):
- What is this project? (→ `mission.md`)
- What are the current priorities? (→ `roadmap.md`)
- What's the tech stack?
- How is the code organized? (top-level packages, major modules)

Populate `mission.md` and `roadmap.md` from the answers.

## Step 4: Identify Module Boundaries

Walk the directory structure. Identify the natural charter boundaries — one charter per logical domain, not one per file.

Good boundaries:
- A top-level package or directory with a clear responsibility
- A group of files that change together
- A subsystem with its own data model or external dependencies

For a typical project, expect 3–8 charters.

## Step 5: Generate Skeleton Charters

For each module boundary, create a charter file in `charters/`. Use `_template.md` for structure and study the [worked example](reference-notes/example-project.md) for density and tone.

For each charter:
- Start with **Owns** (what this module is responsible for) and **Does Not Own** (what belongs elsewhere). "Does Not Own" is load-bearing — it prevents scope creep and tells the agent where boundaries are. Every charter needs both.
- For each public function or class:
  - Read the actual code
  - Document: what it does (one line), what it reads/writes, callers (←), callees (→)
  - Flag any tripwires (!) — non-obvious behavior, intentional workarounds, things that look wrong but aren't
- Each function entry should be 3–5 lines. If it's longer, you're over-documenting. If it's one line, you're probably missing access patterns or cross-references.

Don't invent. Extract from the code. If you're unsure about intent, ask the Architect or mark it with `?`.

**Sizing**: Charters are a small map, not a mirror. A single charter should typically be 30–80 lines. If it exceeds ~100 lines, split it into two domains. The total charter set is typically 3–6% of the codebase by line count (a 75K-line codebase → ~4,500 lines of charters across 20 files). Smaller projects trend higher — that's normal, because charters carry design intent that outweighs the code. Oversized charters defeat the purpose — they consume the context window they're supposed to save. The real test: can the agent load the cross-cutting charter plus 1–2 module charters alongside the code being changed?

## Step 6: Build the Index

Populate `charters/INDEX.md` mapping code paths → charter files:

```
| If you're changing... | Read these charters |
|---|---|
| `src/auth/` | [Auth](auth.md) + [Cross-Cutting](cross-cutting.md) |
| `src/api/` | [API](api.md) + [Cross-Cutting](cross-cutting.md) |
```

## Step 7: Write the Cross-Cutting Charter

This is the most important charter. Read the [cross-cutting section in charters/README.md](charters/README.md#the-cross-cutting-charter) for the full rationale and study the [worked example](reference-notes/example-project.md) for format.

It documents patterns that span modules:
- Multi-module data flows (show the full chain, not just one hop)
- Implicit contracts between modules (things not encoded in function signatures)
- Invariants that must hold across all code paths
- Synchronized implementations (if you change one, you must change the other)

Label dangerous patterns with `TRIPWIRE`. Every cross-cutting charter should have at least one. If you can't find any tripwires, you haven't looked hard enough — ask the Architect what keeps them up at night.

## Step 8: Verify

After bootstrap, check:
- [ ] Every major module has a charter
- [ ] INDEX.md maps code paths to charters
- [ ] Cross-cutting charter exists with at least one TRIPWIRE
- [ ] `mission.md` and `roadmap.md` are populated
- [ ] The Architect has reviewed and corrected anything off

## What "Done" Looks Like

The system is bootstrapped when the next code change can follow the normal loop:
1. Agent reads relevant charters before changing code
2. Agent makes the change grounded in charter context
3. Agent updates charters after the change
4. The cycle improves from here — monotonically

## Reference

→ [Identity and Ownership](reference-notes/identity-and-ownership.md) — solo vs. team repo context (read before Step 1)
→ [Worked Example](reference-notes/example-project.md) — a complete populated Gator for a simple Python project
→ [Gator Charter Schema v1](docs/charter-schema-v1.md) — the official public charter schema
→ [Charter Formation Process](docs/charter-formation-process.md) — the official public trailblazing process
→ [Charter Format](charters/README.md) — notation, philosophy, anti-patterns
→ [Constitution](constitution.md) — the rules that govern ongoing work after bootstrap
