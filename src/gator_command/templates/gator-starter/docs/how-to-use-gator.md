# How to Use Gator

A practical guide for new users. This walks you through installing Gator, governing your first repo, and using the knowledge layer that makes AI coding sessions architecturally coherent.

## Install

```
pipx install gator-command
```

This gives you the `gator` CLI. Verify it works:

```
gator --version
```

## Govern Your First Repo

Navigate to any Git repository you want to govern:

```
cd your-project
gator gatorize .
```

This creates a `.gator/` folder inside your repo. That folder is the governance layer — it contains everything Gator uses to keep your AI coding sessions grounded in shared understanding.

After gatorizing, you'll see this structure:

```
your-project/
  .gator/
    constitution.md        <- the rules your AI agent follows
    mission.md             <- what this project is and why it exists
    roadmap.md             <- current priorities
    inbox.md               <- quick idea capture
    commit_draft.md        <- tracks what changed and why (per commit)
    charters/              <- the intelligent map of your codebase
    blueprints/            <- feature flow maps
    threads/               <- lightweight evolving topics
    active-threads/        <- topics currently being worked on
    artifacts/             <- deep records, design docs, analyses
    procedures/            <- repeatable workflows
    policies/              <- coding conventions and standards
    reference-notes/       <- cognitive aids and vocabulary
    field-guides/          <- language-specific pattern sheets
    vault/                 <- sensitive files (gitignored, never committed)
    scripts/               <- Gator's enforcement and tooling scripts
    whiteboard.md          <- ephemeral surface for review findings
```

Most of `.gator/` is committed to Git, but not all of it. The durable knowledge layer travels with the code; machine-local operational residue does not.

Tracked examples:
- `mission.md`, `roadmap.md`, `charters/`, `threads/`, `docs/`, `artifacts/`, `session-snippets/`

Gitignored local-only examples:
- `vault/`
- `commit_draft.md`, `whiteboard.md`, `status.json`
- `product-source.json`
- `active-vendor-session.json`
- `session-blocks/`
- `diagnostics/`
- `sessions/_active/`

This split is intentional: repo knowledge and durable evidence stay in Git, while machine-local state, sensitive material, and ephemeral workflow residue stay off-branch.

## Bootstrap: Your First Session

The first time you open an AI coding session in a gatorized repo, the model reads the constitution and sees that charters are empty. It will walk you through the bootstrap process:

1. **Establish project identity.** The model asks what your project is and populates `mission.md` and `roadmap.md`. These anchor every future session.

2. **Scan for existing knowledge.** If your repo already has `ARCHITECTURE.md`, ADRs, module READMEs, or AI instruction files (`.cursorrules`, etc.), the model offers to migrate that knowledge into `.gator/` structures.

3. **Identify module boundaries.** The model walks your directory structure and proposes how to divide the codebase into logical domains — typically 3-8 charters.

4. **Generate initial charters.** For each domain, the model reads the code and creates a charter: what the module owns, what it doesn't own, key functions, their access patterns, and any non-obvious behavior (tripwires).

5. **Build the index.** The model creates `charters/INDEX.md` — a dispatch table mapping code paths to charter files so any future session knows where to look.

6. **Write the cross-cutting charter.** This documents patterns that span multiple modules: data flows, implicit contracts, invariants. It is the most important charter in any set.

You don't need to do this manually. Just start a session and the model handles it. But you should review the output — the bootstrap is a conversation, and your corrections make the charters accurate.

## The Normal Loop

After bootstrap, every coding session follows the same loop. You don't need to ask for this — the model does it because the constitution tells it to.

**Session opening.** The model reads the constitution, mission, roadmap, inbox, and last commit draft. It picks up where the last session left off.

**Before changing code.** The model reads the relevant charters (found via `INDEX.md`) to understand the module it's about to touch — what functions exist, what they read and write, what depends on them, and what's dangerous.

**Making the change.** The model writes code grounded in charter context. It knows the invariants, the boundaries, and the tripwires.

**Updating charters.** Immediately after editing each code file, the model updates the affected charter. New functions get entries. Changed access patterns get updated. Removed functions get deleted. This is part of the edit, not an afterthought.

**Logging the change.** The model appends what happened to `commit_draft.md` — what changed, why, and what type of change it was.

**Committing.** When you authorize the commit, a pre-commit hook fires automatically. It checks that charters were updated alongside code, that the commit draft is populated, and writes a status snapshot. If something is missing, the commit is blocked and the model tells you why.

This loop is what makes AI coding sessions produce coherent software instead of disconnected code generation. The model can't just write code — it has to demonstrate understanding before and after.

## What You Can Ask For

A gatorized repo gives your AI agent a rich set of capabilities beyond just writing code. Here's what's available and how to ask for it.

### Charters — The Codebase Map

Charters are compressed operational maps of your codebase. Each one covers a module and documents its functions, their access patterns, dependencies, and dangerous behavior.

You can ask:

- "Show me the charter for the auth module"
- "What functions write to the database in this module?"
- "What depends on this function?" (the model checks `←` cross-references)
- "What would break if I changed this?" (the model traces the dependency graph)
- "Are there any tripwires I should know about before touching this file?"

The model maintains charters automatically as part of coding. You can also ask it to regenerate or improve them:

- "The charter for [module] feels thin — can you flesh it out?"
- "Add tripwire documentation for [that tricky pattern we just discussed]"

### Blueprints — Feature Flow Maps

Blueprints show how features work end-to-end, referencing the modules and functions involved. They're optional — create one when you need to understand or explain a feature's full path through the system.

- "Create a blueprint for the checkout flow"
- "How does authentication work end-to-end? Write a blueprint."
- "Which charters are involved in the payment processing flow?"

### Threads — Tracking Evolving Ideas

Threads are lightweight notes (5-20 lines) for topics that have momentum but aren't ready for a full design document. They persist across sessions so context isn't lost.

- "Create a thread about the caching strategy we've been discussing"
- "This conversation about error handling has momentum — save it as a thread"
- "What threads do we have open right now?"

Active threads live in `active-threads/` and are checked at session start. When a topic is resolved, threads move to `threads/` for reference.

### Artifacts — Deep Records

Artifacts are the long-form thinking layer. Design documents, research analyses, strategic assessments, implementation plans, post-mortems. Date-prefixed and permanently stored.

- "Write an artifact analyzing the trade-offs between approach A and approach B"
- "Create a design document for the new API layer"
- "Document what we just decided about the database migration as an artifact"

### Procedures — Repeatable Workflows

Procedures capture workflows that have stabilized — the kind of thing you'd otherwise explain from memory each time. Step-by-step, with checkpoints where a human should verify.

- "We've done this deployment process three times now — write it up as a procedure"
- "Document the release process as a procedure for next time"
- "What's the procedure for [task]?"

### Policies — Standing Rules

Policies are coding conventions and standards that apply consistently. They solve the problem of AI agents forgetting your preferences between sessions.

- "Create a policy: we always use structured logging, never print statements"
- "Write a policy for our naming conventions"
- "We never use mocks in integration tests — save that as a policy"

### Reference Notes — Cognitive Aids

Reference notes are stable definitions, vocabulary, and reference material. Things you want to look up rather than things you want to track.

- "Write a reference note explaining our event sourcing pattern"
- "Document our API versioning scheme as a reference note"
- "I keep explaining this concept to AI agents — save it as a reference note"

### Field Guides — Language-Specific Patterns

Field guides are condensed pattern references organized by language. Each has an agent-facing pattern sheet and a human-facing tutorial with real code snippets.

- "Generate a field guide for the Python patterns used in this repo"
- "What patterns does the JavaScript field guide recommend for error handling?"

### Inbox — Zero-Friction Capture

The inbox is the lowest-ceremony way to capture an idea. Anything you mention that doesn't belong in a specific place can go here.

- "Add to the inbox: we should consider rate limiting on the public API"
- "Inbox this: the cache invalidation logic might have a race condition"

The model checks the inbox at session start, so nothing gets lost.

### Vault — Sensitive Storage

The vault is gitignored — files placed here never leave your machine. Use it for credentials, large files, or private material.

- "Save this API key to the vault"
- "Put this PDF in the vault so I can reference it during the session"

## The Dashboard

Gator includes a local dashboard for managing your governed repos:

```
gator dashboard
```

This opens a browser-based interface where you can:

- See all your governed repos at a glance
- Browse each repo's knowledge layer (charters, threads, artifacts, etc.)
- Search across documents
- View file and commit history
- Check Gator version and upgrade

The dashboard reads from your local Git repos — it doesn't send data anywhere.

## Upgrading

Check for updates and upgrade from the dashboard, or manually:

```
pipx upgrade gator-command
```

After upgrading, run `gator gatorize .` in each governed repo to update the scripts and templates.

## Key Concepts

**The constitution** governs how AI agents behave in your repo. It defines the loop, the rules, and the roles. You can customize it, but the defaults work well out of the box.

**Charters are the core innovation.** They are not documentation in the traditional sense. They are compressed operational maps written by AI models for future AI models, with the human using them as an audit surface. They force the model to externalize its understanding of the codebase, making that understanding inspectable and correctable.

**The pre-commit hook is the enforcement mechanism.** It ensures that code changes and charter updates stay synchronized. Without it, the discipline would degrade under the speed of AI generation. With it, the governance loop is mechanical, not aspirational.

**Knowledge lives in the repo, not in model memory.** AI models have their own memory systems, but those are invisible to other users and other models. Everything important goes in `.gator/` so it's shared, versioned, and durable.

**You are the Architect.** You hold mission, taste, and architectural coherence. The AI agents propose; you decide. The system is designed to keep you in control of intent and direction even when implementation moves at model speed.
