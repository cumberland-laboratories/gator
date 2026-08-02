---
title: Positioning Hierarchy
created: 2026-06-03
source: ChatGPT blind review (2026-06-02)
---

# Positioning Hierarchy

Canonical vocabulary for all marketing, documentation, and positioning. Adopted from ChatGPT blind review — the first external reviewer to correctly classify Gator.

## The Frame

| Level | Term | What it means |
|-------|------|---------------|
| **Category** | AI coding governance | The market space Gator defines. Not "AI coding assistant," not "context framework," not "memory system." Governance. |
| **Product** | Gator | The thing you install. Includes the per-repo harness and Gator Command (the cross-repo control plane). |
| **Method** | Navigation coding | The practice of maintaining structured maps (charters) alongside code, updated as code changes. The human-readable layer that makes AI work inspectable. |
| **Mechanism** | Constitutions, charters, hooks, trailers, command post, enforcer | The six primitives that implement the governance loop. |

## How to Use This

- **README / landing page**: Lead with the category. "AI coding governance" is the positioning statement.
- **Docs**: Explain the method (navigation coding) before the mechanism. Users need to understand the practice before the tooling makes sense.
- **Technical writing**: Use "mechanism" when referring to the six primitives collectively. Don't conflate product and method — "Gator" is the product, "navigation coding" is what you do with it.
- **Comparisons**: Position against the category, not against individual tools. Gator doesn't compete with Cursor or Copilot (assistants) or with AGENTS.md (instruction files). It governs the work those tools produce.

## Connections

→ [Business Model](../active-threads/business-model.md) — where this hierarchy lives as a strategic decision
→ [artifact](../artifacts/2026-06-02-chatgpt-blind-review-gator-1.md) — source review
