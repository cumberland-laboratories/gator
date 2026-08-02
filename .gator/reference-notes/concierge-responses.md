# Concierge Responses

When the Memex is working well, the Architect should feel like they're working with someone who deeply knows the project, the process, and the context. That means the agent handles orientation questions naturally — not with a docs dump, but with a concise, grounded answer that draws from the knowledge layer.

This maps common Architect questions to where the answers live and how to frame them.

## How to Use This

When the Architect asks a question that matches a pattern below, read the referenced files and synthesize a response. Don't recite file contents — answer like a colleague who knows everything. Be concise. Offer to go deeper if the Architect wants.

---

## Orientation and Workflow

### "What happened last session?" / "Catch me up"

**Draw from**: `commit_draft.md`, `inbox.md`, `whiteboard.md`, `issues.md`

**Frame as**: Summarize commit draft entries (what changed, who decided), any new inbox items, unresolved whiteboard findings, and open issues. The goal: make the Architect feel like the conversation never ended.

### "Why is git status still dirty?" / "Did the commit fail?" / "Why are commit_draft and whiteboard modified?"

**Draw from**: `reference-notes/expected-governance-residue.md`, constitution commit-hook section

**Frame as**: Explain expected governance residue. After a successful Gator commit, `.gator/commit_draft.md` and `.gator/whiteboard.md` may appear modified because the hooks reset or clear them for the next session. That is expected housekeeping, not unfinished product work.

### "What should I work on?" / "Where do I start?"

**Draw from**: `roadmap.md`, `inbox.md`, `issues.md`, `commit_draft.md`

**Frame as**: Check roadmap for current priorities, issues for blockers, inbox for captured ideas. Suggest the highest-priority item. Ask if priorities have shifted.

### "What are we building?" / "What's the mission?"

**Draw from**: `mission.md`

**Frame as**: The mission in the Architect's own words. If stale or vague, flag it and offer to refine together.

### "What's the priority?" / "What's next?"

**Draw from**: `roadmap.md`

**Frame as**: Present top items by status. Suggest the next concrete step for the highest-priority active item.

---

## Research and Knowledge

### "What do we know about [topic]?"

**Draw from**: `active-threads/`, `threads/`, `artifacts/` — search by title, tags, and cross-references

**Frame as**: Start with the thread summary (2-4 sentences). Offer to go deeper into the thread or follow connections. If no thread exists, say so and suggest creating one if the topic has momentum.

### "What connects to [topic]?"

**Draw from**: Thread cross-references, artifact connections

**Frame as**: Follow the annotated links. Show the Architect the connection graph outward from their topic. Cross-references explain *why* the link exists — surface that.

### "Create a thread for this" / "Let's capture this"

**Draw from**: `active-threads/_TEMPLATE.md` (if exists), constitution thread rules

**Frame as**: Create the thread with a Summary and Connections section. Place in `active-threads/` if it has current momentum, `threads/` if it's reference. The test: "if we came back to this next week, would this help us resume?"

### "This thread is getting long" / "This should be an artifact"

**Draw from**: Constitution compression rules (60-line trigger)

**Frame as**: If over 60 lines, either split (distinct subtopics that stand alone) or move depth to an artifact and leave a stub. Preserve cross-references. Nothing is deleted — depth moves, it doesn't disappear.

---

## Codebase (for coding projects)

### "How does [module] work?" / "Explain [this code]"

**Draw from**: Relevant charter(s) via `charters/INDEX.md`, then the actual code

**Frame as**: Start from the charter — what the module owns, doesn't own, key functions, data flows. Then go to code for specifics. Charter gives the overview; code gives the detail.

### "I don't understand this code" / "I'm rusty on [language]" / "Walk me through this"

**Draw from**: `.gator/field-guides/` (if a guide exists for the language), then relevant charters, then the code

**Frame as**: If a field guide exists for the language, mention it: "We have a [language] field guide that covers the patterns used in this repo — want me to pull it up?" If no guide exists but the repo qualifies (≥2 charters covering that language), offer to generate one. If the repo doesn't qualify, walk through the code directly using charter context. Never assume the Architect wants a field guide — some prefer to read the code directly.

### "Is it safe to change [X]?" / "What would break?"

**Draw from**: Charter `←`/`→` annotations, `cross-cutting.md` TRIPWIREs

**Frame as**: Check callers, callees, tripwires. Give a concrete blast radius. Suggest an enforcer review if the change touches cross-cutting patterns.

### "Run the enforcer" / "Check this" / "Review my changes"

**Draw from**: `procedures/enforcer-review.md`, enforcer configuration

**Frame as**: Clarify what they want — the enforcer review script (`python .gator/scripts/enforcer-review.py`, sends diff + charters to a model) or a CLI enforcer (separate model in a separate terminal for full independence). Run it, present findings with context, ask the Architect what to do. Do not start fixing things.

### "Are the charters up to date?" / "Check for charter drift" / "Do the charters match the code?"

**Draw from**: Charter alignment procedure, charters, code

**Frame as**: Three levels of the charter alignment procedure. Level 1 (agent, 30 sec): grep charter `### func()` entries against covered files — catch renames and deletions. Level 2 (Architect triggers the enforcer review script): model reads diff + relevant charters via INDEX, checks boundaries, TRIPWIREs, and drift. Level 3 (Architect triggers a CLI enforcer): full repo-wide audit with a separate model, all charters vs all code, no diff needed. The pre-commit hook also catches the most common drift patterns mechanically: blocks commits without charter updates, warns on stale function references, warns on undocumented new functions.

### "How do I set up an enforcer?" / "How do I use a different model?"

**Draw from**: Enforcer configuration reference note

**Frame as**: "Enforcer" = the role (a different model auditing work). The enforcer review script (`enforcer-review.py`) is the automated path. Ask three questions — primary agent, available API keys, cost sensitivity — then match to a config. Edit `.gator/scripts/enforcer-config.json` with the provider/model. Supported: anthropic (Sonnet, default), openai (GPT-4o-mini), google (Gemini Flash), ollama (free/local), or none (lint only). Cross-vendor is strongest (different training = different blind spots), but same-vendor is still better than nothing. Help them set the env var, run a test, show them whiteboard.md.

---

## Operations

### "Start the dashboard" / "Launch the dashboard" / "Open the dashboard"

**Draw from**: `reference-notes/dashboard-operations.md`

**Frame as**: Run `python src/gator_command/scripts/gator-dashboard.py`. It starts on port 8420 and opens the browser. Done. Do not attempt to verify the launch or retry — the server stays alive but agent tooling may falsely report it as completed. See the reference note for flags (`--no-open`, `--port`, `--snapshot`, `--repo`).

### "Run gator pulse" / "Show me the pulse"

**Draw from**: `pulse.md`, `scripts/gator-pulse.py`

**Frame as**: Run `python .gator/scripts/gator-pulse.py` to regenerate, then read `pulse.md`. Present the strategic brief.

---

## The Memex Itself

### "What is this memex folder?"

**Frame as**: The Memex is a persistence layer — it makes the AI feel like it was there yesterday. Threads capture topics, artifacts hold depth, the constitution governs how it all works. It grows by being used, not by being configured. Keep it to 2-3 sentences unless they want more.

### "Why do we do it this way?"

**Draw from**: `constitution.md`, `charters/README.md`

**Frame as**: The problem — context is lost between sessions, knowledge rots without governance, and AI generates from stale assumptions without a maintained map. The Memex solves this structurally. Frame in terms of what it does for *this Architect on this project*.

### "Can I change the process?"

**Frame as**: The Architect is the authority. The constitution is a starting point. If something isn't working, change it. The only things that truly matter: the session opening (continuity), capture bias (don't lose thoughts), and the charter loop (for coding projects). Everything else is in service of those. Suggest capturing the change in the constitution so the next session respects it.

---

## Where Things Go

### "Where should I put this?"

**Draw from**: Constitution file purposes table

| What you have | Where it goes |
|---|---|
| A quick idea or observation | `inbox.md` |
| A decision with rationale | Thread |
| Deep research or analysis | `artifacts/` |
| A repeatable workflow | `procedures/` |
| A code-level fact | `charters/` |
| A project direction change | `mission.md` |
| A priority shift | `roadmap.md` |
| A bug or blocker | `issues.md` |
| A recurring rhythm | `patterns.md` |
| A reference or cognitive aid | `reference-notes/` |
| Session change or decision | `commit_draft.md` |
| Sensitive material (credentials, keys) | `vault/` (gitignored) |
| Large files (PDFs, datasets, binaries) | `vault/` (gitignored) |

### "Where do I put sensitive files?" / "Where should credentials go?"

**Frame as**: Use `vault/` (in `gator-command/vault/` for the command post, or `.gator/vault/` in fleet repos). It's gitignored — nothing in vault is ever committed. Use it for credentials, API keys, large files, sensitive docs. Reference vault files from artifacts using `source:` frontmatter. The vault is machine-local. Agents should proactively route sensitive material here instead of to tracked locations.

### "What's the difference between a thread and an artifact?"

**Frame as**: Size and depth. Threads are lightweight (5-20 lines) — a topic with a name, a summary, connections. Artifacts are deep storage — design docs, research, anything that needs space. If a thread grows past ~60 lines, it probably wants to be an artifact.

### "Active thread vs. regular thread?"

**Frame as**: Temperature. Active threads are loaded every session — they're what you're working on this week (5-8 max). Regular threads are reference — loaded on demand when a cross-reference leads there. When a topic cools off, demote it from active to regular. When it heats up, promote it.

---

## Tone Guidance

- **Be a colleague, not a manual.** "The auth redesign thread covers this — here's the key decision" not "According to active-threads/auth-redesign.md..."
- **Lead with the answer, then offer depth.** "That decision was made in March. Want me to pull up the full rationale?"
- **Ground everything in the knowledge layer.** If you're answering from training data rather than the Memex, say so. The Architect should trust that answers come from the actual project state.
- **Flag gaps.** If the Architect asks about something the Memex doesn't cover, say "we don't have a thread on this — should we capture it?" That's the system working.
