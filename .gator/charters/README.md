# Charters

Charters are the comprehension layer for AI-assisted software development. They solve a specific problem: when AI generates code faster than a human can review it, the human loses architectural control — unless there's a structural layer that preserves comprehension at the speed code is now produced.

This folder contains both the philosophy (this document) and the working charters for this project. Point an LLM here and it gets everything: *why* charters exist, *how* they work, the notation system, and real examples it can study and replicate.

**Source**: "Constitutional Architecture for AI-Assisted Software Development" (Cumberland Laboratories, 2026)

---

## The Problem

The bottleneck in AI-assisted development is not code generation. Models are good at writing code. The bottleneck is *comprehension* — the human's ability to understand, evaluate, and direct the system they're nominally in charge of.

Before LLMs, code and comprehension scaled together: you wrote it, so you understood it. AI breaks that coupling. Code volume grows without a corresponding growth in human understanding. The developer becomes a reviewer of output they didn't write, in a codebase that's growing faster than they can read.

This is not a tooling problem. It's a governance problem. The same problem organizations faced when they grew beyond the size where everyone could know everything: you need institutional structures — constitutions, charters, separation of powers — not smarter individuals.

## The Inversion

Traditional documentation describes code. You write the code first, then document it. The documentation is secondary, the code is primary.

Charters invert this relationship.

The charter network — function signatures, access patterns, cross-references, tripwires — is the primary artifact the human works with. It's the layer where architectural decisions are legible, where you can reason about the system without reading every file. The code is the *implementation* of what the charters describe. AI reads the code; humans read the charters; the charters keep them synchronized.

## Session Zero

Every reader — human or LLM — arrives at a codebase with zero history. They don't know why a function exists, what invariants it assumes, or which design decisions look wrong but are intentional.

Code alone doesn't fix this. Code tells you *what* the system does. It doesn't tell you *why* it's shaped this way, *what state it reads and writes*, or *what the system deliberately doesn't do*. These are the things that matter most when you're about to make a change, and they're invisible in the source.

Charters surface what cannot be inferred from reading code:

- **Access patterns**: what a function reads and writes — models, session state, caches, external APIs — so you can predict side effects without reading the body
- **Dependency direction**: what calls this function (`←`) and what it calls (`→`) — so you know what breaks when you change it
- **Tripwires**: the non-obvious patterns that *must* be preserved — rendering dualities, race conditions, intentional workarounds that look like bugs
- **Negative space**: what the system deliberately lacks, stated explicitly to prevent false assumptions

That last point matters especially for LLMs. A model's training data creates priors about what systems "should" have. If your system intentionally omits error retry, or deliberately uses a naive algorithm, the model will "fix" it unless the charter says otherwise. Negative space documentation corrects false priors before they become false code.

---

## The Notation

Each charter covers a code module. Each *function* within that module gets its own block:

```
### get_session_summaries(repo_path, force_refresh)
File: src/gator_command/scripts/gator-session-aggregator.py
Reads snippets, aggregates by (repo, session_id), checks cache, returns summaries.
Filesystem: .gator/session-snippets/*.json (R), ~/.gator/sessions/<path-hash>/ (RW)
<- gator-audit.py --sessions, gator-dashboard.py /api/audit/sessions
-> read_snippets(), aggregate_sessions(), snippet_fingerprint()
! Fingerprint covers full file contents — any byte change invalidates cache.
```

| Symbol | Meaning | Why it exists |
|--------|---------|---------------|
| `function_name()` | Function heading | Greppable identifier — the agent finds the current location via `grep -rn "def function_name"`. Survives code churn without maintenance. |
| `(R)/(W)/(RW)` | Access pattern | Predicts side effects without reading code — `(R)` is safe to call, `(RW)` requires checking downstream effects |
| `!` | Tripwire | Inverts the reader's assumption — contradiction spikes LLM attention at the point of maximum relevance |
| `→` | Outbound cross-reference | "This function depends on..." — follow to understand downstream effects |
| `←` | Inbound cross-reference | "This function is called by..." — follow to understand blast radius |
| `Session R:` / `Session W:` | State access | Tracks untyped state (session dicts, Redis keys) that code analysis alone can't reveal |
| `TRIPWIRE` | Section-level danger label | Flags architectural patterns that span multiple functions and must be preserved as a unit |

**Why function names, not line numbers:** An earlier version of this notation used `[Lnnn]` line anchors. These break on every edit above them, creating combinatorial maintenance overhead. Function names are structurally stable — they survive code churn, they're self-verifying via grep, and they match how LLM agents actually navigate code. The staleness signal is cleaner too: a function name either resolves or visibly fails. A stale line number silently points to the wrong code.

## The Cross-Cutting Charter

The most important charter in any set. It doesn't map to a single code module — it maps to *patterns that span modules*.

Every codebase has behaviors that emerge from the interaction of multiple modules: a data flow that traverses four files, an implicit contract between a prompt and the code that parses its output, an invariant that must be preserved across every exit path. These patterns are invisible in any individual module's charter. They're the things that break during refactors — not because any single module was changed incorrectly, but because the *relationship* between modules was violated.

The cross-cutting charter documents these patterns with `TRIPWIRE` labels. In graph terms, it's a hub node — it connects tightly-clustered domain charters and dramatically improves navigability.

**What goes in the cross-cutting charter:**
- Multi-module data flows where changing one link breaks the chain
- Implicit contracts not encoded in any function signature
- Invariants that must be preserved across all code paths (e.g., "session must be saved on every exit")
- Patterns where two parallel implementations must stay synchronized (rendering dualities, cache/DB consistency)
- Stub inventories — scattered stubs connected by design decisions not yet finalized

**When to read it:** Always. Read the cross-cutting charter first, before the module-specific one.

## How Charters Were Used: A Validated Example

These charters were battle-tested on a 97K-line production Django codebase (20 charter files). They were created *before* a major refactor and served four roles:

1. **Navigation map**: every function, its line number, and its cross-module dependencies — so the agent could trace call chains without reading every file
2. **Dependency graph**: the `←` and `→` annotations show what calls what, so you know what will break when moving code
3. **Tripwire documentation**: the `!` annotations flag dangerous patterns that must be preserved during refactoring
4. **Invariant checking**: after moving code, verify that all charter-documented call paths still work

Three god-function decompositions were completed without regressions. A cross-module CSRF bug was identified via charter cross-references. The enforcer caught 4 stale charters in a single audit run.

## The Three-Layer Documentation Architecture

In a mature codebase, charters are one layer of a three-layer structure:

1. **Charters** — per-module API references. Every public function, its line number, what it reads/writes, what models it touches, session keys, cross-references, and tripwires. Organized by code structure. The machine-readable map.
2. **Designs** — flow-oriented user journey documents. Each one describes a complete business flow (checkout, authentication, quiz-taking) from the user's perspective, referencing charters for technical detail. Organized by what the user does.
3. **Systems** — infrastructure and subsystem documentation. How specific subsystems work (CI/CD, caching, rendering pipeline). Technical reference.

Charters are the ground truth. Designs are generated *from* charters as a more human-readable layer. Systems docs cover the infrastructure charters don't reach.

---

## When to Write Charters

- **At project start**: write skeleton charters alongside skeleton code. They force you to articulate module boundaries before writing implementations.
- **Before onboarding**: when someone new (human or LLM) will parachute into the codebase.
- **Before a refactor**: charters created before a refactor serve as navigation map, dependency graph, and invariant checklist during the work.
- **After a refactor**: module boundaries shift. Update charters to match the new reality, or they become misleading.
- **When an LLM will modify the code**: the charter is the most efficient way to give an LLM the "what goes where" knowledge it needs. It's cheaper than loading every source file into context.

## The Maintenance Obligation

Charters that fall out of sync with code are worse than no charters — a wrong map is more dangerous than no map. This is a structural obligation, not a suggestion.

The update chain: **code change → charter update → design doc update**. If you change a function's signature, access patterns, or cross-references, the charter must be updated in the same operation. Not "later." The charter is part of the change, the same way a migration is part of a schema change.

Because charters use function names (not line numbers), routine code edits that don't change function signatures or behavior don't require charter updates. The maintenance obligation triggers on: renamed functions, changed access patterns, new cross-module dependencies, or new tripwire-worthy behavior. This keeps the overhead proportional to architectural change, not code churn.

## Why Charters Are Especially Effective for LLMs

**Token efficiency.** A charter set compresses a 97K-line codebase into ~20 files of structured notation. The LLM gets the map without paying for the territory.

**Access pattern prediction.** `Models: Submission(R), Grade(W), Enrollment(RW)` tells the LLM exactly what a function mutates without reading a single line of the body. For session state — often an untyped dictionary with hundreds of references across dozens of files — `Session R:` / `Session W:` annotations are the *only* way to track state flow without loading every file.

**Tripwire attention.** The `!` notation exploits how models process text: contradiction spikes attention. When a charter says `! The instructor sees raw_score, but Grade.score is penalty-adjusted — these are different numbers`, the model's prediction is immediately corrected at the point of maximum relevance.

**Negative space correction.** Training-data priors are strong and often wrong for your specific system. A single line saying "no retry logic; failures are intentional signals" prevents the model from "improving" your design. The `TRIPWIRE` label on cross-cutting patterns tells the model "this looks wrong but it's not — preserve it."

## Anti-Patterns

- **Charter as API docs**: charters are about ownership, access patterns, and boundaries, not method signatures. If it reads like a docstring, it's too low-level.
- **Charter without negative space**: the boundaries and "does not own" / tripwire entries are the most valuable parts. Without them, the charter is just a description.
- **Stale charters**: worse than no charters. If you refactor, update or delete the charter. A wrong map is more dangerous than no map.
- **No cross-cutting charter**: if your project has more than 3 module charters and no cross-cutting charter, you're missing the most important one.

## How to Implement Charters in Another Repo

1. **Start with the cross-cutting charter.** Identify multi-module patterns, implicit contracts, and invariants. These are the things that will break first during changes.

2. **Write one charter per code domain.** Not one per file — one per logical domain (e.g., `views_quiz`, `models_core`, `frontend_js`). Each function gets a block with the notation above.

3. **Add a dispatch table** to your project's governance (constitution, CLAUDE.md, or equivalent). The dispatch table maps code paths to charter files: "if you're changing X, read Y."

4. **Make it mandatory.** Add a rule: "before modifying code, consult the relevant charters." Without governance, charters become optional documentation that decays.

5. **Update charters with code changes.** Embed this in your workflow — same commit, same PR, same operation. The charter is part of the change.

For a working example of the full setup, see the charter files in this folder and the [Charter Lookup Procedure](../procedures/charter-lookup.md).

---

## Charters in This Project

### Special Case: The Source `gator-command` Repo

This repo is the source for the public `gator` deploy and the PyPI package. It has two charter surfaces:

- `.gator/charters/` — the authoritative charter set for source-repo script work. These charters describe the scripts that prepare deployment and define shipped governance behavior.
- `.gator/charters/` — the self-governance layer for this repo's own development workflow.

| Charter | Covers |
|---------|--------|
| [scripts-cross-cutting](scripts-cross-cutting.md) | Patterns spanning all script clusters: git() contract, row_key formula, local/remote fallback, SKIP_FILES, import_sibling, plan/execute separation |
| [scripts-command-post](scripts-command-post.md) | Command-post CLI orchestration, shared memex state helpers, deploy pipeline, and spawn thread resolution |
| [scripts-core-library](scripts-core-library.md) | Shared infrastructure: version resolution, repo discovery, registry parsing, path normalization, session schema, machine identity, remote bare-clone cache, output formatters |
| [scripts-fleet-intelligence](scripts-fleet-intelligence.md) | Cross-repo governance: fleet status scan, per-repo intelligence profiles, drift detection, convergence audit dashboard |
| [scripts-session-archaeology](scripts-session-archaeology.md) | Session extraction (Claude, Codex, Gemini), vendor-agnostic orchestration CLI, SQLite/DuckDB/NDJSON sinks |
| [scripts-installer](scripts-installer.md) | Installer and boot chain: gatorize five-scenario dispatch, upgrade/morph, thin link, entry points, registry, command-post boot display |
| [scripts-repo-lifecycle](scripts-repo-lifecycle.md) | Per-repo lifecycle: boot display, template overlay update, charter structural linting |
| [scripts-graph-wiki](scripts-graph-wiki.md) | Thread graph rendering (MediaWiki, Markdown), graph health analysis, automated maintenance crawler |
