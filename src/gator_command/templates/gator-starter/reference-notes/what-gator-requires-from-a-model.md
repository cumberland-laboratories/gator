# What Gator Requires From a Model

Gator is not magic. It is a harness. It improves results when the model behaves in ways the harness can work with.

This note explains the minimum behavioral assumptions behind Gator, why some models benefit more than others, and why short structured instructions outperform one giant prompt file.

## The Core Requirement

Gator works best when the model is willing to:

- read before acting
- treat repo artifacts as authoritative
- follow workflow instructions across multiple steps
- update the knowledge layer after changing code
- distinguish project facts from general priors

In practice, this means Gator is a multiplier on **model discipline**. A strong explorer with poor instruction-following will still miss value that a more disciplined model captures.

## Minimum Behavioral Assumptions

For Gator to work at all, the model does not need to be perfect. It does need a few baseline traits:

### 1. Instruction-following

The model must reliably honor the entry point and the constitution. If it ignores `AGENTS.md`, skips `constitution.md`, or treats the loop as optional, the governance layer collapses into passive documentation.

### 2. Willingness to read structured context

The model must be able to use `mission.md`, `roadmap.md`, charters, and reference notes as working context rather than treating them as decorative docs. Gator assumes the model can navigate from a small map to a relevant local subset.

### 3. Multi-step persistence

The loop is not one instruction. It is a sequence: read, plan, change, update charters, log, lint, optionally review. Gator depends on the model being able to hold that sequence together across a session.

### 4. Respect for repo state over prior assumptions

The model must be willing to replace its generic idea of how software "usually" works with what this repo says is true. This is especially important for `Does Not Own` boundaries and `TRIPWIRE` patterns.

## What Gator Gives a Strong Model

When the model already has good tool use and repo traversal, Gator improves performance in three ways:

### 1. Better orientation

The model starts with a map instead of discovering everything from raw exploration. This reduces cold-start ambiguity and helps the model find the right files faster.

### 2. Better behavioral discipline

The constitution, charters, and reference notes turn good practice into explicit local rules. A model that follows instructions gets a tighter behavioral rail than raw code alone provides.

### 3. Better continuity

The model does not need to reconstruct project intent from scratch each session. Decisions, boundaries, and recurring Architect questions are already captured in repo artifacts.

## Failure Modes

Gator degrades when the model behaves like an undisciplined fast local optimizer.

Common failure modes:

- **Skips the map**: reads code directly, ignores charters, and answers from priors
- **Treats docs as advisory**: follows the code but not the governance
- **Optimizes for immediate completion**: makes the code change but skips charter updates and session logging
- **Hallucinates continuity**: claims knowledge of prior decisions without grounding in repo artifacts
- **Overloads context**: reads too much at once instead of navigating to the relevant subset

These are not failures of the idea. They are failures of harness compliance.

## Why Short Structured Instructions Beat One Giant Prompt

Gator assumes that shorter top-level instructions plus structured repo artifacts outperform a single monolithic instruction file.

Why:

- A short entry point is easier for the model to obey consistently
- The constitution separates global rules from local code knowledge
- Charters localize understanding to the module being changed
- Reference notes answer recurring process questions without bloating the main instruction surface
- The model loads what is relevant instead of dragging every rule into every task

This is why Gator uses a layered structure:

- `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` -- entry point
- `constitution.md` -- global workflow and governance
- `charters/` -- code-local map
- `reference-notes/` -- cognitive aids and repeated explanations
- `threads/` / `artifacts/` -- retained project memory

The goal is not "more instructions." The goal is **better instruction topology**.

## Codex, Claude, and Similar Agents

Agents with strong tool use already perform well through live exploration. Gator helps them by converting some repeated exploration into maintained structure. The better the model is at reading, navigating, and complying with local instructions, the more value Gator adds.

This is why Gator often helps disciplined models more than rogue ones:

- disciplined model + Gator = navigation with accumulation
- rogue model + Gator = some orientation benefit, but much less continuity and governance benefit

Even with a less disciplined model, the structure still creates gravity. A visible constitution, explicit charter index, and dedicated mission/roadmap files make correct orientation easier than in a repo with only raw code and a giant prompt file.

## Practical Test

The practical question is simple:

> Does the model behave as if the repo has a memory and a workflow, or as if every task starts from zero?

If the answer is the first, Gator compounds. If the answer is the second, Gator still helps, but only partially.
