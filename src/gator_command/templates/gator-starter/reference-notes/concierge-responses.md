# Concierge Responses

When Gator is working well, the Architect should feel like they're pair-programming with someone who deeply knows the repo, the process, and the context. That means the primary agent needs to handle orientation questions naturally -- not with a docs dump, but with a concise, grounded answer that draws from the knowledge layer.

This reference note maps common Architect questions to where the answers live and how to frame them.

## How to Use This

When the Architect asks a question that matches a pattern below, read the referenced files and synthesize a response. Don't recite file contents -- answer like a colleague who happens to know everything. Be concise. Offer to go deeper if the Architect wants.

---

## Process and Workflow

### "What's the process here?" / "How does this work?" / "Walk me through the workflow"

**Draw from**: `constitution.md` (The Loop), `procedures/enforcer-review.md`, `reference-notes/workflow-profiles.md`

**Frame as**: The loop is: read charters, propose plan, code, update charters, log to commit draft, significance check (if the change is architecturally significant), mechanical lint, then commit. Enforcer review can happen before coding (check the plan) or after (check the diff) -- both are optional and Architect-driven. The significance check is automatic when triggered -- the agent generates a steelman and flags compatibility implications without being asked. Suggest a workflow profile that matches the project. Walk through it concretely for whatever they're currently working on.

### "How much review do we need?" / "What's the right level of process?"

**Draw from**: `reference-notes/workflow-profiles.md`

**Frame as**: Four profiles from Light to Rigorous. Ask about the project context (solo vs. team, risk level, stakes) and suggest a match. The Architect can escalate per-change -- "this one touches payments, let's be careful" -- without changing the overall profile.

### "What should I do first?" / "Where do I start?"

**Draw from**: `roadmap.md`, `inbox.md`, `commit_draft.md`

**Frame as**: Check roadmap for current priorities, inbox for anything captured since last session, and commit draft for what happened last time. Then suggest the highest-priority item and ask the Architect if that's where they want to start.

### "What happened last session?" / "Catch me up"

**Draw from**: `commit_draft.md`, `inbox.md`, `whiteboard.md`

**Frame as**: Summarize the commit draft entries if present (what changed, who decided what), any inbox items that arrived, and any unresolved whiteboard findings. If `commit_draft.md` is empty, assume the prior commit was rolled over cleanly and use git history plus inbox/whiteboard to reconstruct the latest context. The goal: make the Architect feel like the conversation never ended.

### "Why is git status still dirty?" / "Did the commit fail?" / "Why are commit_draft and whiteboard modified?"

**Draw from**: `reference-notes/expected-governance-residue.md`, constitution commit-hook section

**Frame as**: Explain expected governance residue. After a successful Gator commit, `.gator/commit_draft.md` and `.gator/whiteboard.md` may appear modified because the hooks reset or clear them for the next session. That is expected housekeeping, not unfinished product work.

### "What are we building?" / "What's the mission?"

**Draw from**: `mission.md`

**Frame as**: The mission in the Architect's own words (it was written from their input). If mission.md is vague or outdated, flag it and offer to refine together.

### "What's the priority?" / "What should we work on?"

**Draw from**: `roadmap.md`

**Frame as**: Read the roadmap, present the top items by status. Suggest the next concrete step for the highest-priority "Building" or "Designed" item. Ask the Architect if priorities have shifted.

### "What assumptions are you making?" / "What are you inferring vs. what do you know?"

**Draw from**: Whatever files or code the current answer depends on

**Frame as**: Separate grounded facts from inference explicitly. "The charter says X, the code confirms Y, and I'm inferring Z because [reason]." This is especially important when the Architect is deciding whether to trust a plan, estimate, or code explanation.

### "What's blocking us?" / "Why are we stuck?"

**Draw from**: Current task context, relevant charters, `inbox.md` if prior blockers were captured

**Frame as**: Name the blocker concretely. Is it missing repo knowledge, unclear Architect intent, risky blast radius, environment setup, or a genuine code problem? Then say what information or decision would unblock progress.

### "How big is this?" / "How risky is this?" / "How long will this take?"

**Draw from**: Relevant charters, `cross-cutting.md`, `reference-notes/workflow-profiles.md`

**Frame as**: Estimate in terms of scope and blast radius, not fake precision. "This is a local edit in one module" vs. "this crosses two boundaries and touches a TRIPWIRE." If the work is risky, say why. If the work is small, say what makes it small.

### "Argue against this" / "What could go wrong?" / "Why might this be a bad idea?"

**Draw from**: `procedures/significance-check.md`, relevant charters, `cross-cutting.md`

**Frame as**: Generate the strongest case against the change — not implementation doubts, but architectural and ecosystem-level concerns. Who depends on the current behavior? What changes silently? What migration path exists or doesn't? What secondary effects weren't the stated goal? Present it as a steelman, not a devil's advocate exercise. The Architect should hear the counter-arguments at full strength.

**Note**: The agent should do this automatically (not just on request) for changes touching public API, TRIPWIREs, cross-module invariants, or security-relevant code. See the significance check procedure. But the Architect can also ask for it at any time on any change.

### "Is this a breaking change?" / "What's the semver implication?"

**Draw from**: `procedures/significance-check.md`, relevant charters

**Frame as**: Identify what's public API, what existing consumers depend on, and whether this change would produce different results for code that worked yesterday. Be specific: "ParameterSource is a public IntEnum — changing its values is a semver-major break because user code compares against these values." If there's no public API impact, say so clearly.

---

## Codebase Understanding

### "How does [feature/module] work?" / "Explain [this part of the code]"

**Draw from**: Relevant charter(s) via `charters/INDEX.md`, then the actual code

**Frame as**: Start from the charter -- what the module owns, doesn't own, key functions, data flows. Then go to the code for specifics. The charter gives the 30-second overview; the code gives the detail. Always ground the explanation in what the charter says about boundaries and access patterns.

### "What calls this?" / "What does this depend on?"

**Draw from**: Charter `<-` (callers) and `->` (callees) annotations, `cross-cutting.md` data flows

**Frame as**: Trace the call chain using charter cross-references. Show the Architect the dependency direction and blast radius. If it crosses module boundaries, reference the cross-cutting charter.

### "Is it safe to change [X]?" / "What would break?"

**Draw from**: Relevant charter(s), `cross-cutting.md` TRIPWIREs

**Frame as**: Check the charter for the function -- what calls it (`<-`), what it calls (`->`), any tripwires (`!`). Check cross-cutting for TRIPWIREs that might be affected. Give the Architect a concrete blast radius: "these 3 callers depend on this, and there's a TRIPWIRE about [X]." Suggest an enforcer review if the change touches cross-cutting patterns.

### "Where does [X] happen?" / "Where is [X] defined?"

**Draw from**: `charters/INDEX.md` to find the right charter, then grep the codebase

**Frame as**: Use the index to locate the charter, then the charter to locate the function. Confirm with a grep. Don't make the Architect wait for a full codebase search when the charter already knows the answer.

### "What changed recently in this area?" / "Why is this shaped like this?"

**Draw from**: `commit_draft.md`, relevant threads/artifacts, relevant charters

**Frame as**: Start with recent recorded changes or decisions, then tie them to the current code shape. If the answer is not documented, say so and distinguish "the code does X" from "the rationale is not yet captured."

### "Does this belong here?" / "Which module should own this?"

**Draw from**: Relevant charter `Owns` / `Does Not Own` sections, `cross-cutting.md` if it spans modules

**Frame as**: Answer in terms of ownership, not convenience. "The auth module owns identity checks, but the store module does not own validation." If the current boundaries are unclear, say that clearly and suggest capturing the decision once the Architect chooses.

### "This is a monorepo" / "We have multiple packages" / "How do I charter a tool repo?"

**Frame as**: Monorepos and tool repos (multiple independent packages or tools in one repo) need a slightly different charter structure:

- **One charter per top-level package or tool** -- each major folder gets its own charter in `.gator/charters/`, just like a single-project module would.
- **Keep internals simple** -- for a large package or tool folder, use an internal `README.md` in that folder to explain its local structure and conventions. The top-level charter can point to it for detail.
- **Cross-cutting charter spans the whole repo** -- this is even more important in monorepos. The cross-cutting charter documents how packages interact, shared infrastructure, deployment coupling, and synchronized version requirements.
- **INDEX.md maps paths to charters** -- in a monorepo, the index is the Architect's primary navigation tool. It should map every top-level package directory to its charter.

Example INDEX.md for a monorepo:
```
| If you're changing... | Read these charters |
|---|---|
| `packages/api/` | [API](api.md) + [Cross-Cutting](cross-cutting.md) |
| `packages/web/` | [Web](web.md) + [Cross-Cutting](cross-cutting.md) |
| `packages/shared/` | [Shared](shared.md) + [Cross-Cutting](cross-cutting.md) |
| `tools/cli/` | [CLI Tool](cli-tool.md) |
| `infrastructure/` | [Infra](infrastructure.md) + [Cross-Cutting](cross-cutting.md) |
```

The key principle: charters follow domain boundaries, not file boundaries. A package with 50 files gets one charter. A package with a lot of internal structure can use a local `README.md` to cover the details. Keep the top-level map clean, then work out the rest with the Architect and primary agent based on how the repo is actually shaped.

### "I don't understand this code" / "I'm rusty on [language]" / "Walk me through this"

**Draw from**: `field-guides/` (if a guide exists for the language), then relevant charters, then the code

**Frame as**: If a field guide exists for the language, mention it: "We have a [language] field guide that covers the patterns used in this repo — want me to pull it up?" If no guide exists but the repo qualifies (≥2 charters covering that language), offer to generate one: "We could generate a field guide for [language] — it would document the recurring patterns across the codebase. Want me to check if the repo qualifies?" If the repo doesn't qualify, just walk through the code directly using charter context. Never assume the Architect wants a field guide — some prefer to read the code directly.

### "The code doesn't match the charter" / "Something seems off"

**Draw from**: `procedures/charter-alignment.md`

**Frame as**: Stop. Don't proceed with the current change until the alignment is resolved. Check git history to see whether the charter or the code drifted. Present the discrepancy to the Architect and ask: "Is the charter stale, or is the code wrong?" Then fix whichever one is out of date. See the charter alignment procedure for the full protocol.

### "Are the charters up to date?" / "Check for charter drift" / "Do the charters still match the code?"

**Draw from**: `procedures/charter-alignment.md`, charters, code

**Frame as**: Three levels of charter drift review, escalating in thoroughness:

**Level 1 — Quick check (agent does this, 30 seconds):**
Read each charter's `### func()` entries. Grep the covered files for those function names. If a charter says `### foo()` but `foo` doesn't exist in the code, it's stale. Also check `Covers:` lines — do those files still exist? This catches renames and deletions.

**Level 2 — Enforcer review script (Architect triggers):**
Run `gator hook enforcer-review` — the enforcer review script sends the diff and relevant charters (selected via INDEX.md) to the configured model. It checks boundary violations, TRIPWIRE breaches, missing cross-references, and charter update accuracy. Token-efficient: caches charters across runs, loads only relevant charters via INDEX.

**Level 3 — Full audit (Architect triggers, separate enforcer model or CLI):**
For a repo-wide health check with no diff: the agent suggests the Architect run a CLI enforcer (a different model in a separate terminal) with a custom prompt — the Architect runs it independently; the agent does not invoke the CLI itself. This reads all charters and all code, not just recent changes.

```bash
# Codex
codex review "Read all charters in .gator/charters/. Read the code they cover. Report drift: missing functions, stale entries, boundary violations, broken cross-references."

# Claude
claude --print "Read all charters in .gator/charters/. Read the code they cover. Report any drift."
```

**When to suggest each level:**
- Architect says "quick sanity check" → Level 1
- Architect says "review my changes" or "is this commit safe?" → Level 2
- Architect says "how accurate are the charters?" or "full health check" → Level 3

**The pre-commit hook catches the gap between Level 1 and Level 2 automatically:** it blocks commits where code changed but no charter was updated, warns when charter entries reference functions that don't exist in covered files, and warns when new functions appear in code without corresponding charter entries.

### "How do I set up an enforcer?" / "How do I use a different model for review?"

**Draw from**: `reference-notes/enforcer-configuration.md`, `scripts/enforcer-config.json`

**Frame as**: Ask three questions, then match to a config:

1. **What's your primary agent?** (Claude, Codex, Gemini, etc.)
2. **What API keys or CLI tools do you have?** (Anthropic, OpenAI, Google, or none)
3. **How much do you care about cost?** (Determines model choice)

Then walk them through it:

| Primary agent | Recommended enforcer | Config change |
|---------------|---------------------|---------------|
| Claude (any) | GPT or Gemini (cross-vendor is strongest) | `provider: "openai"` or `"google"` |
| Claude (any) | Sonnet (same vendor, different model — still valuable) | Default config, no change needed |
| Codex / GPT | Sonnet via enforcer-review.py | Default config, no change needed |
| Gemini | Sonnet or GPT | `provider: "anthropic"` (default) or `"openai"` |
| Any | Free local model | `provider: "ollama"`, `model: "llama3"` |
| Any | No model, lint only | `provider: "none"` |

Edit `.gator/enforcer-config.json`:
```json
{
  "layer2_3": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "api_key_env": "ANTHROPIC_API_KEY"
  }
}
```

Help them set the env var, run a test review, and show them where whiteboard.md captures findings. The full decision tree is in `reference-notes/enforcer-configuration.md`.

### "We already have docs" / "There's an ARCHITECTURE.md" / "We have ADRs"

**Draw from**: `gator-start-up.md` (Step 2: Scan for Existing Knowledge)

**Frame as**: During bootstrap, scan the repo for existing knowledge before building from scratch. Look for `ARCHITECTURE.md`, `DESIGN.md`, `docs/decisions/`, `docs/adr/`, module READMEs, `.cursorrules`, or any homegrown knowledge folder (`memex/`, `docs/knowledge/`, etc.).

If you find existing material, tell the Architect what you found and suggest where it maps:

| Existing material | Maps to |
|---|---|
| Architecture docs, design docs | `mission.md`, charters, cross-cutting charter |
| ADRs / decision records | Threads (one per decision, preserve rationale) |
| Module READMEs | Seed the charter's "Owns" / "Does Not Own" sections |
| `.cursorrules`, copilot instructions | Review for content that belongs in constitution or reference notes |
| Homegrown charters or knowledge folders | Migrate content into `.gator/` structure |

Don't migrate silently. Show the Architect what you found, suggest the mapping, and ask before copying. Some material may be outdated or intentionally separate from Gator.

### "My CLAUDE.md is really long" / "Will Gator work with a big instruction file?"

**Frame as**: Be honest. Gator is designed and tested with short entry points — 5-10 lines that point to the constitution. The installer appends a Gator section to existing files, but if the file is very long (100+ lines of custom instructions, skills, personas), there is a real risk that the model's attention to the Gator pointer degrades. We have not tested Gator's efficacy when the entry point is buried deep in a large instruction file.

**What to suggest**:

1. **Best option**: Move the Gator pointer to the top of the file. The constitution reference should be one of the first things the model reads, not something it encounters after 200 lines of other instructions.
   ```markdown
   # Project Entry Point

   Read [`.gator/constitution.md`](.gator/constitution.md) before your first response. It governs how you work here.

   If this is a **fresh project** (charters/ is empty or contains only templates), follow the bootstrap procedure in [`.gator/gator-start-up.md`](.gator/gator-start-up.md).

   ---

   [... rest of existing instructions below ...]
   ```

2. **Acceptable option**: Keep the Gator section clearly demarcated (the installer uses a `# --- Gator Navigation Coding ---` marker) and ensure the model reads it. Test by asking "what does the constitution say?" early in a session — if the model doesn't know, the pointer isn't landing.

3. **What to avoid**: Leaving the Gator pointer at the very bottom of a long file and hoping for the best. Models handle the beginning and end of long prompts better than the middle, but "better" is not "reliably."

**The honest caveat**: Gator's progressive-disclosure architecture (short entry point → constitution → charters on demand) depends on the entry point actually being read. If the entry point is competing with 500 lines of other instructions, the whole governance layer may not activate. When in doubt, keep the entry point short and at the top.

---

## Enforcer and Review

**Terminology reminder**: "Enforcer" = the role (a different model). "Enforcer review script" = `enforcer-review.py` (the automated tool). "Charter alignment procedure" = the process for detecting/resolving code-charter drift. See the constitution's Terminology table.

### "How do I set up the enforcer?" / "How do I run a review?"

**Draw from**: `reference-notes/enforcer-configuration.md`, `procedures/enforcer-review.md`

**Frame as**: Ask the three questions (primary agent, available keys/tools, cost sensitivity), then walk them through the matching setup. The enforcer review script (`enforcer-review.py`) is the primary automated path. CLI enforcers (Codex, Claude, Gemini in a separate terminal) are the independent-verification path. See the enforcer configuration reference note for the full decision tree.

### "What did the enforcer find?" / "Show me the review"

**Draw from**: `whiteboard.md`

**Frame as**: Read the latest review entry from the whiteboard. Present findings with context -- what the finding means, which charter or TRIPWIRE is involved, what the options are. Then ask the Architect what to do. Do not start fixing things.

### "Is this ready to commit?" / "Are we good?"

**Draw from**: `whiteboard.md` (any unresolved findings), `commit_draft.md` (completeness), charter update status

**Frame as**: Check three things -- (1) are there unresolved HIGH/CRITICAL whiteboard findings? (2) does the commit draft capture what changed? (3) were the charters updated for any code changes? If all three are clean, say so. If not, flag what's missing.

### "Are you following the process?" / "Did you actually read the charters first?"

**Draw from**: The actual files read in-session, current task context, `constitution.md`

**Frame as**: Answer directly and concretely. "Yes -- I read `constitution.md`, then `charters/INDEX.md`, then [specific charter]." Or: "Not yet; I need to read [file] before I can answer responsibly." The Architect should never have to guess whether the agent is operating inside the loop.

### "Should we run a review on this?" / "Is this worth an enforcer pass?"

**Draw from**: Relevant charters, `cross-cutting.md`, `reference-notes/workflow-profiles.md`

**Frame as**: Tie the answer to risk and blast radius. Suggest no review for routine local edits; suggest a plan review or diff review when the change touches boundaries, TRIPWIREs, or cross-cutting behavior. The point is calibrated review, not maximal review.

### "Check the auth module" / "Does the code match the charters?" / "Review [module] for me"

**The enforcer is not limited to diff review.** CLI-based enforcers (Codex, Gemini, Claude) can do any charter-grounded audit the Architect asks for -- with or without a diff. These broad charter-vs-code audits are run by the Architect independently in a separate terminal — `enforcer-review.py` is diff-oriented and can't do them. The agent's role is to *suggest* the invocation, not run the CLI itself. Examples the agent can suggest:

| Architect says | Architect runs (agent suggests) |
|---------|------------|
| "Does the code still match what the charters say?" | `codex review "Read all charters in .gator/charters/. Read the code they cover. Report any places where the code has drifted from what the charters describe."` |
| "Review the store module against its charter" | `codex review "Read .gator/charters/store.md. Read the code it covers. Report any functions missing from the charter, any stale entries, and any TRIPWIRE violations."` |
| "Are there any charter gaps?" | `codex review "Read all charters and INDEX.md. Walk the codebase. Report any code modules that have no charter coverage."` |
| "Check for boundary violations" | `codex review "Read all charters, focusing on 'Does Not Own' sections. Check the code for cases where a module does something its charter says it shouldn't."` |
| "How accurate are our charters?" | Full charter-vs-code audit -- health check, not a diff review |

These don't require uncommitted changes. They're general-purpose charter-grounded audits. The enforcer reads the charters, reads the code, and reports what it finds. The Architect can ask for this at any time -- not just before a commit.

**For the Python script**: `enforcer-review.py` is specifically designed for diff-based review — and it is the primary agent's only enforcement path. For broader audits, the agent suggests the Architect run a CLI enforcer (Codex, Claude, Gemini) with a custom prompt in a separate terminal. The Architect frames the question and runs it; the enforcer does the reading.

**Frame as**: "The enforcer can do more than check your latest changes. Want me to hand you the command so you can audit [module/area] against the charters in a separate terminal?"

### Enforcer Layers and Strategies -- What to Suggest

When the Architect asks about review options, the primary agent should be able to explain the layers and suggest the right strategy:

**Layer 1 -- Mechanical lint** (instant, free, deterministic):
- Catches: hardcoded secrets, SQL dangers, injection risks, TODO markers, .env files
- When to suggest: "This runs automatically before every commit. It's your safety net for things that should never ship."

**Layers 2-3 -- Charter-grounded model review** (costs tokens, takes time, catches architectural issues):
- Catches: boundary violations, TRIPWIRE breaches, stale charters, missing cross-references, blast radius
- When to suggest: "If this change touches boundaries, invariants, or cross-cutting patterns, a model review is worth it. For routine edits, Layer 1 is usually enough."

**Strategy suggestions by context:**

| Situation | Suggest |
|-----------|---------|
| Routine edit, single module | Layer 1 only (automatic) |
| Touching a TRIPWIRE or cross-cutting pattern | Full review (Layer 1 + model) |
| Large refactor or boundary change | Pre-code review of the plan + post-code review of the diff |
| Architect wants a health check, no changes pending | General audit (charter-vs-code, no diff needed) |
| About to merge to main | Full review at minimum |

### "Can I run the enforcer myself?" / Running the enforcer in a separate terminal

**Yes -- and it's the strongest trust guarantee.** The Architect runs the enforcer independently, in a separate terminal, and sees the output directly with no intermediary.

**What to tell the Architect:**

Open a new terminal in the project directory and run one of these:

```bash
# Codex CLI (use the dedicated enforcer prompt explicitly)
codex review "Read .gator/.includes/reference-notes/enforcer-prompt.md for full instructions. Review the uncommitted changes against the charters."

# Or with a specific prompt
codex review "Read .gator/constitution.md and all charters in .gator/charters/. Review the uncommitted changes against the charters. Report findings with severity levels."

# Claude Code
claude --print "$(cat .gator/.includes/reference-notes/enforcer-prompt.md)"

# Gemini CLI
gemini < .gator/.includes/reference-notes/enforcer-prompt.md
```

**What the external enforcer agent should know:**

When running a CLI enforcer in a separate terminal, the agent picks up its instructions from:
1. **`.gator/.includes/reference-notes/enforcer-prompt.md`** -- the full enforcer prompt: what to read, what to check, output format
2. **`AGENTS.md`** -- the primary-agent entrypoint for Codex; useful project context, but not the enforcer role definition

For a custom audit (not just diff review), the Architect can prompt the enforcer directly:

```
Read .gator/constitution.md for governance rules.
Read all charter files in .gator/charters/ (start with INDEX.md).
Read the code covered by those charters.
[Your specific question -- e.g., "Are there boundary violations?", "Which charters are stale?", "Does the cross-cutting charter still reflect reality?"]
Report findings with severity levels (CRITICAL/HIGH/MEDIUM/LOW).
```

**The key point for the Architect**: the enforcer in a separate terminal has no memory of what the primary agent did or said. It reads the repo fresh. That's the independence guarantee -- different model, different session, different perspective.

**Frame as**: "You can always run the enforcer yourself in another terminal. It reads AGENTS.md or the enforcer prompt, checks the code against the charters, and gives you findings directly. No intermediary. Want me to show you the command for your setup?"

---

## Operations

### "Start the dashboard" / "Launch the dashboard" / "Open the dashboard"

**Draw from**: `reference-notes/dashboard-operations.md` (if present)

**Frame as**: Run `gator dashboard`. It starts on port 8420 and opens the browser. Done. Do not attempt to verify the launch or retry -- the server stays alive but agent tooling may falsely report it as completed. See the reference note for flags (`--no-open`, `--port`, `--snapshot`, `--repo`).

### "How do I gatorize a repo?" / "What's gatorize?" / "Install gator"

**Frame as**: "Gatorize" means install or upgrade Gator in a repo. Run `gator gatorize <target-directory>` (or `gator gatorize .` from inside the repo). This is the canonical cross-platform installer — Windows, macOS, and Linux. The installer creates `.gator/`, installs hooks, writes entry points, and registers the repo. It's safe to run on an already-gatorized repo (upgrade mode).

### "How do I add an existing repo to the Dashboard?" / "I pulled a gatorized repo but it's not in my Dashboard"

**Frame as**: Run `python gatorize.py <path-to-repo>`. If the repo already has `.gator/` (e.g., a colleague gatorized it and pushed to ADO/GitHub), gatorize detects this as an update (scenario 3) — it refreshes hooks and templates non-destructively, then registers the repo in your local command post's `registry.md`. After that, the Dashboard sees it. This is the standard "add a repo to my local fleet" workflow. No data is lost, no branches are changed, existing `.gator/` content is preserved.

### "Run gator pulse" / "Show me the pulse"

**Draw from**: `pulse.md`, `scripts/gator-pulse.py`

**Frame as**: Run `gator pulse` to regenerate, then read `pulse.md`. Present the strategic brief.

---

## Gator Itself

### "I just cloned Gator" / Agent detects it is inside the Gator repo itself

**How to detect**: `README.md` describes Gator as "a harness for AI coding" AND `install.sh` exists at the root. This means you are inside the Gator starter kit, not a project that uses Gator.

**Frame as** (gently — the Architect may be confused):

"It looks like we're inside the Gator repo itself — this is the starter kit, not a project that uses Gator. Most Architects want to install Gator into a different repo. Here's how:

1. Open a terminal
2. Run: `bash install.sh /path/to/your/project`
3. Then open your project in a new AI session — the agent will find the constitution and start the bootstrap

If you'd like, I can help you run the installer right now. What's the path to the project you want to install Gator into?"

If the Architect actually wants to work on Gator itself (contributing, customizing, studying the architecture), that's also valid — proceed with the existing charters and constitution. Ask: "Are you looking to install Gator into another project, or are you working on Gator itself?"

Don't assume. Ask. Some Architects are here to use the tool; others are here to study or improve it.

### "What is this .gator folder?" / "What is Gator?"

**Draw from**: `constitution.md`, `README.md`

**Frame as**: Gator is a self-improving knowledge layer for the codebase. Charters are a small, intelligent map (typically 3-6% of the codebase) that the agent reads before every change and updates after. The constitution defines how it works. It's navigation coding -- the opposite of vibe coding. Keep it to 2-3 sentences unless they want more.

### "Why do we do it this way?" / "What's the point of [charters/constitution/enforcer]?"

**Draw from**: `charters/README.md` (philosophy), `constitution.md`

**Frame as**: The problem -- AI generates code faster than humans can review it. Without a structural layer, the Architect loses architectural control. Charters solve this by keeping the human's comprehension in sync with the code at the speed it's now produced. The constitution ensures the loop doesn't decay. The enforcer provides independent verification. Frame it in terms of what it does for *this Architect on this project*, not abstract theory.

### "Can I change the process?" / "Do I have to follow all of this?"

**Frame as**: The Architect is the authority. The constitution is a starting point, not holy writ. If something isn't working for them, change it. The only thing that truly matters is the loop: read charters -> make change -> update charters. Everything else is in service of that. Suggest capturing the process change in the constitution so the next session respects it.

### "Why does this feel different from normal prompting?" / "Why is it asking me so many questions?"

**Draw from**: `reference-notes/why-navigation-coding-feels-different.md`, `mission.md`

**Frame as**: Navigation coding relocates judgment upstream. The agent asks more specific questions because the point is to resolve ambiguity before code is written, not after regressions appear. The friction is part of the safety mechanism, not accidental ceremony.

### "Will this work with [model/tool]?" / "How much does this depend on the model behaving well?"

**Draw from**: `reference-notes/what-gator-requires-from-a-model.md`

**Frame as**: Gator helps any model more if it follows instructions well. Explain the baseline assumptions: read before acting, treat repo artifacts as authoritative, update the knowledge layer, and operate as if the repo has memory. Be honest if a weaker or more rogue model will get less value.

### "What's the cleanest enforcer setup for my primary agent?" / "Which enforcer path should we prefer?"

**Draw from**: `reference-notes/enforcer-configuration.md`, `procedures/enforcer-review.md`

**Frame as**: Distinguish between "works" and "cleanest." For example: if Codex is primary and the Architect wants Anthropic as enforcer, the cleanest path is `enforcer-review.py` with `provider: anthropic`, because Claude Code CLI in the same repo also sees `CLAUDE.md` as a primary-agent entrypoint. If the Architect wants a separate Claude terminal anyway, say that it works, but explain the role-overlap trade-off.

---

## Where Things Go

### "Where should I put this?" / "What's inbox for?" / "When do I use a thread?"

**Draw from**: `constitution.md` (File Purposes table)

The Architect (or agent) has information and needs to know where it lives. Quick decision guide:

| What you have | Where it goes | When |
|---------------|--------------|------|
| A quick idea, observation, or "we should..." | `inbox.md` | Anytime. Zero friction. Append and move on. |
| A decision with rationale worth preserving | `threads/` | When the topic has a name and you'd want to find it next week |
| A deep design doc, research, or analysis | `artifacts/` | When it needs more than 20 lines and permanence |
| A repeatable workflow that's stabilized | `procedures/` | When you've done it twice and will do it again |
| A code-level fact (function, boundary, tripwire) | `charters/` | Every code change -- this is mandatory |
| A project direction or identity statement | `mission.md` | When the "what" or "why" of the project changes |
| A priority shift | `roadmap.md` | When what's next changes |
| A recurring rhythm or obligation | `patterns.md` | When something happens on a schedule |
| A reference, vocabulary, or cognitive aid | `reference-notes/` | When it helps orient someone (human or model) |
| A session change or decision | `commit_draft.md` | Every code change, every decision, during the session or branch; clear after commit |
| Enforcer review findings | `whiteboard.md` | Written by the enforcer script automatically |
| Sensitive material (credentials, keys, tokens) | `.gator/vault/` | Immediately. Never commit sensitive material. Vault is gitignored. |
| Large files (PDFs, datasets, binaries) | `.gator/vault/` | When referenced by artifacts or threads but too large for git |

### "What's the difference between a thread and an artifact?"

**Frame as**: Size and depth. Threads are lightweight (5-20 lines) -- a topic with a name, a summary, and some cross-references. They exist so a decision or observation doesn't have to be re-explained every session. Artifacts are deep storage -- design docs, research, analysis, anything that needs space. If a thread grows past ~60 lines, it probably wants to be an artifact.

### "What goes in the roadmap vs. inbox?"

**Frame as**: Roadmap is *prioritized and structured* -- items with status, ordered by importance. Inbox is *zero-friction capture* -- anything goes, no formatting needed. Ideas start in inbox; when they're real enough to prioritize, they graduate to roadmap. The agent can suggest promotions, but the Architect decides.

### "When do I update mission.md?"

**Frame as**: Rarely. Mission changes when the fundamental "what" or "why" of the project shifts. If you're just refining priorities, that's roadmap. If you're pivoting, that's mission. Most sessions never touch it.

### "What's patterns.md for?"

**Frame as**: Recurring rhythms -- deploy schedules, standup cadences, release cycles, recurring obligations. Things that happen on a schedule and need to be remembered across sessions. If the project has no patterns yet, leave it empty.

### "Should we capture this?" / "Is this worth writing down?"

**Draw from**: `constitution.md` (capture bias), the file-purposes table

**Frame as**: If the information would help resume work next week, capture it. Then route it: inbox for quick ideas, thread for named decisions, artifact for depth, charter for code facts, roadmap for priority, mission for project-direction changes. Err toward capture rather than loss.

### "Where do I put sensitive files?" / "Where should credentials go?" / "This file is too big for git"

**Frame as**: Use `.gator/vault/`. It's a gitignored directory inside `.gator/` — nothing in vault is ever committed. Use it for:

- **Credentials, API keys, tokens, certificates** — anything the layer-1 lint would flag
- **Large files** — PDFs, datasets, images, binaries that artifacts or threads reference but that don't belong in git history
- **Sensitive research** — proprietary docs, NDA material, internal reports

Organize by subdirectory if needed (e.g., `.gator/vault/certs/`, `.gator/vault/data/`). Reference vault files from artifacts using `source: .gator/vault/filename` in frontmatter. The vault is machine-local — it doesn't transfer when someone clones the repo. If a vault file needs to be shared, that's a team-level decision outside Gator's scope.

**Key rule for agents**: If you encounter or generate sensitive material during a session, write it to `.gator/vault/`, never to a tracked location. The pre-commit lint will catch common secrets, but the vault is the proactive discipline.

### "Is the knowledge layer stale?" / "What should we clean up in .gator/?"

**Draw from**: `commit_draft.md`, relevant charters, `whiteboard.md`, `reference-notes/workflow-profiles.md`

**Frame as**: Be specific about the kind of staleness: missing charter updates, outdated roadmap priorities, uncaptured decisions, oversized threads, unresolved whiteboard findings. Suggest the smallest cleanup that restores trust in the map.

---

## Tone Guidance

- **Be a colleague, not a manual.** "The store module owns persistence -- here's how the data flows" not "According to the charter located at .gator/charters/store.md..."
- **Lead with the answer, then offer depth.** "That function is called from three places. Want me to trace the full chain?"
- **Ground everything in the knowledge layer.** If you're answering from memory or training data, say so. If the charter covers it, cite the charter. The Architect should trust that your answers come from the actual project state, not general knowledge.
- **Flag gaps.** If the Architect asks about something the charters don't cover, say "the charters don't have this -- let me read the code and then we should capture it." That's the loop in action.
