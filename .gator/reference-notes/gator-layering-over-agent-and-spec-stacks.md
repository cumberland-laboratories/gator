# Gator Layering Over Agent and Spec Stacks

Gator should not position itself as a replacement for mature AI coding stacks. It should position itself as the governance and comprehension layer that sits on top of them.

This matters because many modern repos already have strong local machinery for prompting, subagents, workflows, specs, tasks, memory, or orchestration. Gator works best when it governs that machinery rather than competing with it.

## Core Position

Use this framing:

- other AI stacks decide how agents work
- Gator decides how governed work is framed, checked, recorded, and reviewed

In practice:

- let the local AI stack keep its commands, skills, prompts, subagents, and workflows
- add `.gator/` as the repo's governance layer
- route the agent through constitution + charter expectations
- keep deterministic commit gates and enforcer review outside the prompt loop

## The Split of Responsibilities

### Agent / workflow stacks

These systems usually provide:

- prompt and command surfaces
- subagents or role specialization
- skills, routines, workflows, or orchestration
- local memory and tool integrations
- planning or execution accelerators

They answer questions like:

- how should the agent execute work?
- which command starts the workflow?
- how do subagents coordinate?
- how does the tool integrate with MCP, editors, browsers, or shells?

### Gator

Gator provides:

- constitution-level agent operating rules
- charters as the shared code comprehension layer
- deterministic charter-alongside-code enforcement
- separate-model enforcer review
- trailer-based audit evidence
- command-post and fleet governance when needed

It answers questions like:

- what rules govern the agent in this repo?
- what code understanding must persist as the code changes?
- what has to be updated when code changes?
- what deterministic gates block silent drift?
- how is review separated from writing?
- how does governance travel across sessions, models, and repos?

## Layering Rule

If a repo already has a strong AI stack, Gator should follow this rule:

1. Preserve the existing execution stack.
2. Install `.gator/` without rewriting that stack.
3. Make the existing agent entrypoints respect Gator governance.
4. Let the local stack keep doing the operational work.
5. Require that meaningful code changes still pass Gator governance.

Short version:

- local stack inside
- Gator outside

## Example 1: Agentic Workflow Stack

Example: `shanraisshan/claude-code-best-practice`

This kind of repo is centered on capability and orchestration:

- commands
- agents
- skills
- hooks
- MCP servers
- workflows
- agent teams
- worktrees
- memory and settings

Gator should not try to replace that surface.

Instead:

- keep `.claude/` and related tool-specific structure intact
- add `.gator/` as the governance layer
- let `CLAUDE.md` remain the user-facing entrypoint
- require the agent to read constitution and charters before coding
- enforce charter updates and audit trails at commit time

The positioning line is:

- that stack helps agents do more
- Gator helps humans govern what agents do

## Example 2: Spec / Planning Stack

Example: `github/spec-kit`

This kind of repo is centered on spec-driven development:

- project principles
- specifications
- technical plans
- task breakdowns
- implementation flows
- extensions and presets

Gator should not try to replace that planning system.

Instead:

- let the spec stack own pre-code intent, decomposition, and tasking
- let Gator own implementation governance and post-plan discipline
- use charters as the living code map once implementation begins
- use enforcer review and commit gates to keep the code, the map, and the review trail aligned

The positioning line is:

- the spec stack decides what to build and how to stage it
- Gator governs how implementation stays legible, reviewed, and auditable

## Example 3: Cross-Tool Harness Stack

Example: `affaan-m/ECC`

This kind of repo is centered on harness optimization across many tools:

- shared rules and prompts
- commands and skills
- hooks and adapters
- MCP and tool integrations
- local memory/context systems
- cross-tool install targets
- performance and security tuning

Gator should not try to replace that harness layer.

Instead:

- keep the cross-tool harness intact
- add `.gator/` as the stable governance surface inside each governed repo
- let ECC continue to optimize execution, routing, and capability
- let Gator govern what counts as acceptable repo work
- keep audit trails, charter sync, and review separation outside the harness prompt loop

The positioning line is:

- ECC optimizes the agent harness
- Gator governs the work produced through that harness

## Differentiation

Gator needs a sharp answer to "how is this different from other AI repo frameworks?"

The answer is not "more commands," "better prompts," or "more powerful agents."

The answer is:

- Gator is about governance, not harness performance
- Gator is about comprehension persistence, not just context stuffing
- Gator is about deterministic repo discipline, not just workflow convenience
- Gator is about review boundaries, not just execution capability
- Gator is about Git-native audit evidence, not just local productivity

### What Others Usually Optimize

Most adjacent stacks optimize for:

- better prompts
- more commands
- stronger agent orchestration
- richer integrations
- spec and task generation
- faster execution

Those are real benefits, but they are not Gator's category.

### What Gator Optimizes

Gator optimizes for:

- human supervision that survives fast AI coding
- code understanding that persists across sessions and models
- a living map of module ownership and tripwires
- deterministic friction when code and understanding diverge
- independent review from a different trust boundary
- durable governance records inside Git itself

### The Category Line

When comparisons start drifting toward tools, stacks, or prompt systems, pull back to category:

- those systems help agents act
- Gator helps humans govern agent action

Or more formally:

- those systems improve the execution layer
- Gator governs the execution layer

### What Gator Is Not

Gator is not:

- a replacement for Claude Code, Codex, Gemini, Cursor, or ECC
- a prompt library
- a subagent marketplace
- a spec generator
- a task runner
- a workflow orchestrator
- a memory hack

Gator can coexist with all of those.

### What Gator Adds Even When Those Exist

Even in a repo that already has excellent workflows, prompts, and orchestration, Gator still adds:

- constitutions that tell agents how to work in the repo
- charters that preserve code comprehension as structure changes
- commit-time enforcement that code and charter updates travel together
- separate-model enforcer review
- trailer-level audit metadata
- fleet-level governance when many repos are involved

## Important Non-Goals

Gator should not:

- replace mature command or subagent ecosystems
- replace spec, plan, or task frameworks
- replace cross-tool harness frameworks
- require a blank repo with no existing AI conventions
- collapse local memory/orchestration systems into Gator's own structures
- present itself as the single operating system for all AI coding behavior

That framing creates unnecessary competition and weakens the layering story.

## Integration Pattern

When governing an existing AI-heavy repo, the preferred pattern is:

1. Detect the existing stack first.
2. Preserve its directory structure and user-facing workflows.
3. Add Gator's governance layer with minimal disruption.
4. Update the tool entrypoints so the agent reads:
   - constitution
   - charter lookup guidance
   - commit and review rules
5. Keep local commands, skills, subagents, and specs available as execution tools.
6. Use Gator for:
   - code comprehension persistence
   - deterministic gating
   - review boundaries
   - audit evidence

## Why This Positioning Is Strong

This framing lets Gator win where it is strongest:

- governance
- comprehension
- review separation
- drift prevention
- auditability
- cross-model continuity

It also lets other stacks keep what they are already best at:

- orchestration
- prompting ergonomics
- spec generation
- task decomposition
- tool integrations
- workflow acceleration

## Concierge Implication

The concierge should learn to recognize these stacks and adapt.

Examples:

- "Govern this Claude Code repo without breaking its subagents."
- "Install Gator on top of this Spec Kit project."
- "Keep the existing slash-command workflow, but add charter enforcement."
- "Map this spec-driven repo into Gator governance without replacing its planning flow."

That is a better product story than asking users to abandon the systems they already like.

## Practical One-Liner

Use this when needed:

`Gator is the governance and comprehension layer that sits on top of your existing AI coding stack.`

## Connections

- -> [Repo Layer Charter Authority](repo-layer-charter-authority.md) - avoids collapsing repo layers when reasoning about governance
- -> [Refactor Approach](refactor-approach.md) - example of a concierge flow Gator should govern rather than replace
- -> [Positioning Hierarchy](positioning-hierarchy.md) - broader product and messaging structure
