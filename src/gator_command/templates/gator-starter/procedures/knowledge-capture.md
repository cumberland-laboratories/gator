# Procedure: Knowledge Capture — Where Things Go

## Context

AI models have built-in memory systems (Claude's `MEMORY.md`, Gemini's memory, Copilot's context, etc.). These systems are designed to persist information across sessions for a single user on a single model. They are **invisible** to other users and other models working in the same repo.

Gator repos are designed to work across multiple users and multiple AI models. The `.gator/` folder is the shared knowledge layer. If repo knowledge ends up in a model's personal memory instead, it creates information silos that defeat the purpose of the system.

## The Decision Rule

When you learn something worth remembering, ask: **"Is this about the project or about the person?"**

### Goes in `.gator/` (shared, visible to all)

- Architectural decisions and their rationale
- Code invariants, constraints, tripwires
- Module boundaries and ownership
- Data flows and access patterns
- Bug context, incident notes, post-mortems
- Project priorities, milestones, deadlines
- Patterns that span modules
- Anything a different user or model would need to work here effectively

**Where in `.gator/`:**

| What you learned | Where it goes |
|---|---|
| Something about a function or module | Charter update |
| A decision with rationale | Thread |
| A pattern or invariant spanning modules | Cross-cutting charter |
| An idea or observation (unstructured) | `inbox.md` |
| A priority shift | `roadmap.md` |
| A project direction change | `mission.md` |
| A recurring obligation or rhythm | `patterns.md` |

### Goes in model memory (personal, per-user)

- The user's communication preferences (terse vs. verbose, etc.)
- The user's role and expertise level
- Workflow habits specific to one person
- Editor or tooling preferences

### When in doubt

Put it in `.gator/`. A redundant note in `inbox.md` costs nothing. Knowledge trapped in one model's memory is invisible and eventually lost.

## Common Mistakes

**Saving an Architect decision to memory instead of a thread.** The next model won't know about it. The next user won't know about it. The decision will be relitigated.

**Saving a tripwire to memory instead of a charter.** The whole point of tripwires is that they protect everyone. A tripwire only one model knows about protects no one.

**Saving project context to memory instead of `mission.md` or `roadmap.md`.** This creates drift — different models and users develop different understandings of what the project is and where it's going.

## For Model-Specific Entry Points

If you maintain a model-specific entry point file (e.g., `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`), it should point the model to the constitution and `.gator/` as the primary knowledge source. Model-specific instructions in these files should be limited to behavioral configuration (how to invoke tools, formatting preferences), not project knowledge.
