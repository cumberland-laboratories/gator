# Constitution

This document governs how you work in this project. Read it at session start. Follow it exactly.

## Roles

| Role | What it does |
|------|-------------|
| **Architect** | Human. Holds mission, taste, architectural coherence. All decisions. |
| **Agent** | Reads and writes the .gator/ knowledge layer in-session. Updates charters, captures ideas, maintains the knowledge layer. |
| **Enforcer** | Different model. Read-only audit. Produces reports, does not edit. |

## The Loop

This is a closed-loop system. The agent's workflow on every code change:

1. **Before changing code**: read the relevant charters (use `.gator/charters/INDEX.md` to find them)
2. **Propose the plan**: explain what you're about to do, grounded in charter context
3. *(optional)* **Pre-code enforcer review**: the Architect may request an enforcer check of the plan against charters before any code is written
4. **Make the change**: write code grounded in what the charters say about invariants, access patterns, and neighbors
5. **Immediately after editing each code file, update the affected charter** — before editing the next file, before running tests, before moving on. This is part of the edit, not part of the commit. Update: new functions, changed access patterns, new cross-references, removed entries. If you touched code and haven't touched a charter, you are not done with the edit.
6. **Log the change**: append a bullet to the body of `commit_draft.md` and update the YAML frontmatter (`message`, `change-type`, `significance`, `decision-tags`, `agent`, `architect`)
7. **Significance check**: if the change touches public API, cross-module invariants, TRIPWIREs, or security-relevant code, generate a steelman argument against the change and flag compatibility implications. Surface to the Architect before committing. See [`procedures/significance-check.md`](procedures/significance-check.md). Skip for routine edits.
8. **Commit**: stage files and run `git commit`. Two deterministic hooks fire automatically:
   - **Pre-commit** (`gator-pre-commit.py --phase validate`): validates charter-alongside-code (blocks if code changed but no charter updated), checks commit_draft is populated, writes `.gator/status.json`. Findings go to `whiteboard.md`.
   - **Commit-msg** (`gator-pre-commit.py --phase trailers`): assembles the full commit message from `commit_draft.md` (`message` field becomes the summary line, session change log entries become the body) and appends Gator-* metadata trailers. Falls back to the agent's `-m` message if the draft is empty.
   - **Post-commit** (`gator-pre-commit.py --phase cleanup`): resets `commit_draft.md` and clears stale `whiteboard.md` findings after a successful commit.
   The agent does not run these scripts directly — git runs them. If the pre-commit hook blocks, read `whiteboard.md` for the reason and present it to the Architect.
   **Expected governance residue**: after a successful commit, `.gator/commit_draft.md` and `.gator/whiteboard.md` may appear modified because the hooks reset or clear them for the next session. This is expected housekeeping, not unfinished product work. For the fuller decision procedure on which `.gator/` changes to commit after ANY Gator-driven modification (`gator update`, `gator gatorize`, session work), see [`procedures/committing-gator-files.md`](procedures/committing-gator-files.md). For handling of `.pre.gator*` rollback backups produced by a v1→v2 layout migration, see [`procedures/pre-gator-residue.md`](procedures/pre-gator-residue.md). For merge conflicts in `.gator/` files, branches on different Gator versions, or origin ahead/behind on Gator content, see [`procedures/gator-version-drift.md`](procedures/gator-version-drift.md) — do not ask the operator which version wins; the procedure has the full resolution rules.
9. *(optional)* **Post-code enforcer review**: the Architect may request a full charter-grounded enforcer review of the diff before committing

Steps 1, 2, 4, 5, 6 are the default workflow. A code change without a charter update is incomplete — and the pre-commit hook enforces this structurally. Step 7 (significance check) runs automatically when triggered — the agent does not need Architect prompting for this; it's the agent's responsibility to notice when a change is significant. Step 8 (commit with hooks) runs by default. Steps 3 and 9 are Architect-driven — the agent does **not** run charter-grounded reviews unprompted. The Architect controls the cadence and weight of model-based review.

The right level of review depends on the project and the change. See [`reference-notes/workflow-profiles.md`](reference-notes/workflow-profiles.md) for suggested profiles from Light (no review) to Rigorous (multiple reviews, cross-vendor). The Architect picks the profile — or mixes and matches per change.

## Charter Rules

- **Always read the cross-cutting charter first** (`.gator/charters/cross-cutting.md`, when it exists). It documents multi-module invariants — the patterns that break during refactors because the *relationship* between modules was violated. Then read the module-specific charter via `.gator/charters/INDEX.md`.
- Charters use **function names** as identifiers (not line numbers). Grep-verifiable, survives code churn.
- Every charter entry includes: what the function does, what it reads/writes, what calls it (`←`), what it calls (`→`), and tripwires (`!`) for non-obvious behavior.
- The `.gator/charters/INDEX.md` maps code paths → charter files. The agent maintains it.
- If the code appears to deviate from what a charter describes, **stop and resolve the discrepancy before proceeding**. Check git history to determine whether the charter or the code drifted. Present the discrepancy to the Architect. See [`procedures/charter-alignment.md`](procedures/charter-alignment.md).
- Format reference: [`.gator/charters/README.md`](charters/README.md)

## Session Opening

At the start of every session:
1. Read this constitution
2. Read `.gator/mission.md` (what we're building)
3. Read `.gator/roadmap.md` (current priorities)
4. Check `.gator/inbox.md` (anything captured since last session)
5. `.gator/commit_draft.md` is commit-message plumbing — it is gitignored and reset after every commit, so at session open it is normally the empty stub. Do not read it as a session-opening surface. Check it only if you have reason to think the previous session left uncommitted work.
6. Check charter health: if `.gator/charters/` is empty or has no real charters, follow the Charter Bootstrap Procedure → [`.gator/gator-start-up.md`](gator-start-up.md) before beginning substantial coding work

Make the human feel like the conversation never ended. For common Architect questions — "what's the process?", "catch me up", "is this safe to change?" — see [`reference-notes/concierge-responses.md`](reference-notes/concierge-responses.md). For post-commit worktree confusion, see [`reference-notes/expected-governance-residue.md`](reference-notes/expected-governance-residue.md).

## File Purposes

| File | Purpose | When to update |
|------|---------|---------------|
| `.gator/mission.md` | What we're building and why | When the project direction changes |
| `.gator/roadmap.md` | Priority-ordered feature list | When priorities shift |
| `.gator/inbox.md` | Zero-friction idea capture | Anytime — append freely |
| `.gator/commit_draft.md` | Source of truth for commit messages: `message` field becomes the summary line, session change log becomes the body. Also drives Gator-* trailers. | Every code change, every decision; cleared to stub after commit |
| `.gator/patterns.md` | Recurring rhythms, obligations, schedules | When patterns emerge |
| `.gator/charters/` | The intelligent map of the codebase (3–6% by line count) | Every code change (mandatory) |
| `.gator/blueprints/` | Per-feature flow maps — how features work, referencing charters and modules | When the Architect wants system-level comprehension |
| `.gator/threads/` | Lightweight reference notes on topics | When a topic has momentum |
| `.gator/pulse.md` | Strategic operations brief — generated by `gator-pulse.py` | Run `gator pulse` to regenerate |
| `.gator/artifacts/` | Deep records, design docs, research | When depth is needed |
| `.gator/procedures/` | Repeatable workflows | When a process stabilizes |
| `.gator/field-guides/` | Language-specific pattern sheets + Architect tutorials | Manual regeneration when patterns drift |
| `.gator/reference-notes/` | Cognitive aids, vocabulary, examples | When reference material helps |
| `.gator/whiteboard.md` | Ephemeral working surface (enforcer findings) | During review, cleared after |
| `.gator/vault/` | Sensitive material and large files (gitignored, never committed) | When handling credentials, keys, PDFs, datasets |
| Enforcer review (`gator hook enforcer-review`) | Charter-grounded linter (3 layers), runs from the installed Gator CLI | Architect-requested, agent-invoked |

## Threads

Threads live in `.gator/threads/` and `.gator/active-threads/`. They are lightweight (5–20 lines) and carry:
- `## Summary` (2–4 sentences, self-contained)
- `## Connections` (annotated cross-references — why the link exists)

Threads don't need to be long. They exist to give a topic a name and a place. Active work goes in `.gator/active-threads/`; completed or parked threads move to `.gator/threads/`.

## Compression

The .gator/ folder should stay lean. If a thread exceeds 60 lines, consider splitting or moving detail to an artifact. If an artifact grows, that's fine — artifacts are deep storage.

## Terminology

| Term | Meaning |
|------|---------|
| **Enforcer** | The *role* — a different AI model that audits the primary agent's work. Read-only. |
| **Enforcer review script** | `enforcer-review.py` — the automated tool that sends diffs + charters to a model and writes findings to `whiteboard.md`. Architect-triggered, not automatic. |
| **Charter alignment procedure** | The process for detecting and resolving code-charter drift. Three levels: quick check (agent grep), model review (enforcer review script), full audit (CLI enforcer). See [`procedures/charter-alignment.md`](procedures/charter-alignment.md). |
| **Pre-commit hook** | The mechanical gate (`gator-pre-commit.py`) — runs automatically on every `git commit`. No model. Deterministic. |
| **Gatorize** | Install or upgrade Gator in a repo. Run `gator gatorize <target-directory>` (or `python gatorize.py <target-directory>` from a source checkout). This is the canonical installer. |
| **Gator** | The product: Git-native governance for AI-assisted engineering. Ships as `pipx install gator-command`. Includes repo-native governance, hook enforcement, repo comprehension, local Dashboard, and the `gator loop` multi-agent primitive. Apache 2.0. |
| **Enterprise capability** | Optional feature activated via `gator enterprise setup` — connects a governed repo to an org's Enterprise control-plane server (`.gator/enterprise.json` marker). Adds fleet-scale evidence, audit, policy rollout, and centralized reporting. Not a separate product; a subcommand group in the same wheel. **Current state (Phase 4e, 2026-08-02)**: the base wheel ships a thin dispatcher only — the enterprise-cli package is source-checkout-only (`pip install ./enterprise/enterprise-cli/`). The `[enterprise-server]` extra installs server-side dependencies (FastAPI, SQLAlchemy, Alembic) for operators running the Enterprise API service; it does NOT install the CLI. A single-pipx install path is post-cutover packaging work. |
| **Memex** | Legacy knowledge-layer format. If `memex/` or `.memex/` directories exist in a repo, they are from a previous system. Gator is the successor. Content can be migrated into `.gator/` structures manually or with agent assistance. Do not create new Memex structures. |

## Enforcer Findings Are for the Architect

When enforcer findings arrive, the agent **presents them to the Architect and asks for direction**. The agent does not silently fix findings, dismiss them, or start acting on them unprompted.

**How to run enforcers** (trust boundary):
- **Enforcer review script**: `gator hook enforcer-review` — the canonical enforcement path. Sends the diff + relevant charters to the configured enforcer model and writes findings to `whiteboard.md`, the authoritative Architect-visible record. The trust boundary here is **behavioral**: the agent reads the findings, presents them to the Architect, and does not act on them unprompted (see "Enforcer Findings Are for the Architect" below). The script also prints findings to stdout, so it is *not* a hard visibility barrier against the primary agent — for fully independent review where the agent never sees the findings, the Architect runs an enforcer in a separate terminal.
- **Never** run a CLI enforcer directly (e.g., `codex review --uncommitted`) from the primary agent session — that bypasses the `whiteboard.md` record and the structured review path. Route the agent's enforcement through `enforcer-review.py`; independent CLI review is the Architect's to run.

The correct behavior:
1. Run the enforcer via the enforcer review script (`enforcer-review.py`)
2. Read `whiteboard.md` for findings
3. Summarize the findings clearly to the Architect
4. Offer context: what the finding means, what charter or TRIPWIRE is involved, what the options are
5. **Ask the Architect what to do next**

This is deliberate. Enforcer findings are a forcing function for the Architect to think deeply about what's happening in the code. The value isn't just the fix — it's the Architect's understanding that comes from deciding *whether* and *how* to fix it.

## Project Assessment

When the Architect asks for a project assessment, write a 2-paragraph expert evaluation to `.gator/artifacts/YYYY-MM-DD-project-assessment.md`. Write as an expert consultant advising an engineering manager — direct, evidence-based, actionable.

**Format:**
```
---
date: YYYY-MM-DD
type: project-assessment
model: <your model name>
---

## Project Assessment

[Paragraph 1: current state — what's working, what's built, where the project stands]

[Paragraph 2: what's needed — priorities, risks, recommendations for the path forward]

— <model name>, YYYY-MM-DD
```

The next `gator pulse` run will include the latest assessment automatically.

## Knowledge Lives in the Repo

Many AI models maintain per-user memory systems (Claude's `MEMORY.md`, Gemini's memory, etc.). These are external to the repo and invisible to other users and other models. **Repo knowledge belongs in `.gator/`, not in model-specific memory.**

The `.gator/` folder is the shared knowledge layer — it works across users, across models, across sessions. If you learn something about this codebase that would help the next person (or the next model) work here, it goes in the repo:

- Decisions, invariants, patterns → `.gator/charters/`, `.gator/threads/`, or `.gator/inbox.md`
- Project context and priorities → `.gator/mission.md`, `.gator/roadmap.md`
- Ideas and observations → `.gator/inbox.md`

See [`procedures/knowledge-capture.md`](procedures/knowledge-capture.md) for the full decision guide.

## Field Guides

Field guides are optional language-specific pattern references in `.gator/field-guides/`. Consult when writing new code in a language that has a guide — same cadence as reference-notes (situational, not always-loaded). If no guide exists for a language, that's normal. Generation procedure: → [`procedures/field-guide-generation.md`](procedures/field-guide-generation.md)

## What You Don't Do

- Don't create documentation for code that the charters already cover
- Don't defer the charter update to commit time — update it immediately after each file edit, as part of the same mental operation
- Don't treat this folder as optional context — it's the primary working surface
- Don't save repo knowledge to model-specific memory instead of `.gator/`
- Don't act on enforcer findings without Architect direction — present, suggest, ask
