---
last-touched: 2026-03-18
category: essay
hits: 1
tags: [memex-infrastructure, tooling, graph-health, scaling, enhancements, essay]
---

> *Memex architecture essay — preserved from this reference instance's earlier development as the Memex about the Memex. Not a working thread for the active project; historical thinking about the architecture itself.*

# Memex Enhancements

## Summary

Near-term improvements to close the gap between the Memex's constitutional claims and its operational reality. Derived from the ChatGPT hostile review, the internal scaling analysis, and the knowledge-systems thread. Four priorities, ordered by leverage — scoped to graph-health and schema issues. The hostile review's retrieval-axis critique (#7) and labor/latency critique (#8) are tracked in the knowledge-systems and agent-performance threads respectively, not here.

## Plan

### 1. Graph-health instrumentation — DONE

**What**: `scripts/graph_health.py` — a standalone companion to `memex-lint.sh` that reports backlink index, 3-hop reachability violations, single-bridge edges, and optionally renders a graph visualization (`wiki/thread-graph.png`). Uses networkx for graph operations, matplotlib for rendering. `memex-lint.sh` continues to handle orphan detection and cross-reference integrity.

**Why**: The constitution claims graph connectivity as an invariant. The hostile review's sharpest line: "the repo is selling theoretical navigability before proving it." This makes the claim testable. Every run produces evidence.

**Answers hostile critique**: #3 (correctness not yet by design), #4 (claims asserted not demonstrated).

### 2. Schema tightening

**What**: Audit every frontmatter field, artifact template, and procedure for machine-checkable constraints. Eliminate prose-only exceptions — if a rule has an exception, encode the exception in the schema so the lint script can verify it.

**Why**: ChatGPT's balanced review specifically called for "tighten the schema so every exception is machine-checkable rather than prose-explained." The enforcer audit already found contradictions between the artifact schema and the clip procedure. Tightening the schema closes those gaps and makes future audits more precise.

**Answers hostile critique**: #5 (documentation outrunning implementation).

### 3. README vulnerability edit

**What**: Revisit "Encode the rules once, correctness follows by design." Either qualify it honestly or earn it by completing items 1 and 2 first. The hostile reviewer called this the most vulnerable sentence in the repo.

**Why**: The sentence overpromises given current instrumentation. Either the tooling catches up to the claim, or the claim gets softened to match reality. Both are honest; leaving the gap is not.

**Answers hostile critique**: #3 (the most vulnerable sentence).

### 4. Operational history as proof

**What**: Continue operating the Memex across sessions. The thread history, resolved questions, enforcer reviews, and artifact accumulation are themselves the evidence. No special action required — just sustained use.

**Why**: The hostile review's closing recommendation: "show a longer-lived Memex in operation." This is the one thing that can't be accelerated. Every session that updates threads, resolves open questions, and preserves adversarial reviews is building the proof. The repo's git log becomes the rebuttal.

**Answers hostile critique**: #1 (more manifesto than proof), #9 (private operating style not public proof).

## Connections

→ [knowledge-systems-comparison.md](essay-knowledge-systems-comparison.md) — scaling analysis that identified graph maintenance as the failure point; Codex report assessment
→ [agent-performance-latency.md](essay-agent-performance-latency.md) — hostile critique #8 (latency as externalized labor) tracked here
→ [2026-03-18-chatgpt-hostile-review.md](../artifacts/2026-03-18-chatgpt-hostile-review.md) — source of the nine attack lines this plan addresses
→ [2026-03-18-chatgpt-memex-review.md](../artifacts/2026-03-18-chatgpt-memex-review.md) — balanced review with the three highest-value next moves
→ [2026-03-18-power-tool-framing.md](../artifacts/2026-03-18-power-tool-framing.md) — audience and vulnerability framing
→ [tooling-roadmap.md](../reference-notes/tooling-roadmap.md) — tracks planned scripts including Crawler and Spider

## Open Questions

- Should graph-health reporting be an enforcer task, a standalone script, or both?
- What's the right cadence for schema audits — per session, per enforcer run, or triggered by structural changes?
- Does the README edit happen before or after the tooling catches up?
- **Thread creation governance.** How should new threads get created? The constitution says "capture bias" — the agent creates threads when topics have momentum, without asking. But in practice, thread creation is often a give-and-take between adjudicator and primary agent: the human suggests a topic area, the agent proposes structure and scope, the human refines. Is that the right model? Should the agent ever create threads the adjudicator hasn't signaled interest in? Should the adjudicator be able to veto or redirect a thread at creation time? The current answer seems to be: capture bias for organic conversation topics, collaborative creation for structural/system threads. Is that distinction worth encoding?
- **MISSION.md as a scope boundary.** The constitution governs *how* the Memex operates but not *why* or *what belongs*. A mission statement would answer scope questions like "should personal research go in this repo?" For the reference implementation, the mission is self-referential: demonstrate and refine the Memex through its own use. But people cloning the repo will have different missions — research, project management, learning. Should the template include a blank MISSION.md that the operator fills in? Or is this a constitutional addition (a preamble)? The key: the mission constrains what threads get created, which the constitution currently doesn't address.
- **Model-agnostic claim is overstated.** ChatGPT hostile critique #6 is correct — not all models will work as a primary agent or even as an enforcer. The README says "any model that can read markdown and follow instructions can operate the Memex," but in practice models vary significantly in rule-following discipline, cross-reference maintenance, and constitutional adherence. The architecture is model-agnostic; the operating requirements are not. The README should reflect this honestly — perhaps "model-portable" rather than "model-agnostic," or an explicit note that the constitution demands a level of instruction-following that not all models reliably provide.

## Next Up

- Item 2: schema tightening — audit frontmatter and templates for machine-checkable constraints
