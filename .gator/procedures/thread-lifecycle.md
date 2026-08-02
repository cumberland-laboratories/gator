# Procedure: Thread Lifecycle

## Three Layers, One Network

- **active-threads/** — always in context. Live working set. 5–8 files, compression-budgeted.
- **threads/** — not loaded by default. Lightweight nodes (5–20 lines). Navigated via cross-references or tag search.
- **artifacts/** — deep storage. Full synopses, design notes, reports. Referenced like footnotes.

## Thread Format

All threads (active and lightweight) follow this body structure:

```
# Title
## Summary        ← 2-4 sentences. Written for direct extraction by the documentation-render pipeline.
## Detail          ← Dense index-card content (active threads may use domain-specific headings)
## Connections     ← Annotated cross-references
## Open Questions  ← Optional
## Next Up         ← Optional (forward intent, surfaced at next session)
```

The `## Summary` is the key to mechanical documentation rendering. Must be self-contained, readable without the rest of the thread, written at documentation-entry quality. Extracted directly by the render pipeline — no LLM synthesis required.

## Frontmatter Schema

```yaml
---
last-touched: YYYY-MM-DD
category: one-of [mathematics, cognition, systems, ventures, economics, civic]
hits: 0
tags: [list, of, keywords]
---
```

## Rotation (Promotion / Demotion)

- **Demotion** (active → lightweight): When a thread cools off — stops being touched, loses Next Up items, falls out of conversation. Move to `threads/` intact — no compression, no stub creation. The thread is no longer always-loaded, so its length has no context cost. Preserve cross-references.
- **Promotion** (lightweight → active): When a thread heats up — referenced repeatedly, becomes a focus. Expand and move to `active-threads/`.
- **Artifact promotion**: When artifact content keeps surfacing, absorb a working synopsis (3–8 lines) into the referencing thread. The artifact remains as the full record. Don't pre-promote — let repeated use be the signal.

- **Archiving** (active/lightweight → artifact): When the work is concluded — the question was answered, the decision was made, the feature shipped. Move to `artifacts/` as a frozen historical record. The thread becomes a dated snapshot of what happened.

**Invariant**: Graph connectivity is preserved through every transition. Nothing is deleted. Demotion preserves the full thread — no information is lost.

## Splitting

**Trigger**: An active thread exceeds **60 lines** AND contains distinct subtopics that can stand alone.

**Process**:

1. **Identify the seam** — look for `##` sections that address a separable concern. If no clean seam exists, the thread is dense, not bloated — leave it.
2. **Extract** — move the separable section(s) into a new thread (active or lightweight depending on heat). Carry over relevant `tags:` and assign the same `category:`.
3. **Write a Summary** — the new thread must have a `## Summary` before it's complete.
4. **Leave a cross-reference** — in the original thread, replace the extracted content with an annotated link: `→ [New Thread](path.md) — why it was split out`. The original should read as if the split topic was always a separate node.
5. **Verify connectivity** — the new thread must link back to the original and to any other threads the extracted content referenced.

**Two split modes**:

- **Semantic split** (above): distinct subtopics that can stand alone. The test: would a reader ever want one section without the other? If yes, split semantically.
- **Volume split**: the thread is conceptually unified but too dense. Split into `thread-name-1.md` and `thread-name-2.md`. Both share the same Summary, category, and tags. Each cross-references the other as its continuation. No artificial seam required — just a page break.

**Demotion vs. splitting**: Long because one section is cold → demote the cold section (move intact to `threads/`). Long because two hot topics → split semantically. Long because it's just dense → volume split.

## Cross-Referencing

Link to related threads and artifacts using relative paths. Annotate *why* the link exists:

```
→ [Context Budget Economics](context-budget-economics.md) — budget model that governs compaction decisions
```

## Discovery (three mechanisms, in order)

1. **Tags** — grep frontmatter tags. Fast, exact.
2. **See Also** — grep thread content for semantic matches. Slower, broader.
3. **Cross-references** — follow annotated links from within a node. Warm traversal.
