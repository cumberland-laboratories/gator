# Design Note: Background Maintenance

## The Problem

As the thread graph grows, in-session maintenance (hit counting, last-touched updates, cross-reference verification, budget checks, split evaluation) becomes increasingly expensive relative to the conversation it interrupts. Hub threads — nodes with many inbound references — amplify this: touching a hub cascades updates across the graph.

## The Direction

Extend the background subagent pattern from reads to writes. The chat agent flags maintenance events during conversation ("thread X was substantively discussed"). A background process handles the bookkeeping asynchronously:

- Frontmatter updates (hits, last-touched)
- Cross-reference integrity checks
- Budget arithmetic
- Split evaluation triggers

Conversation stays fast. Maintenance runs in the background. The human never sees the bookkeeping.

## When to Implement

Not now. Implement when the friction log shows that in-session maintenance is interrupting conversational flow or consuming noticeable latency. Let the data drive the decision.
