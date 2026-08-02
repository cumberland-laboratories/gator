---
last-touched: 2026-03-17
category: essay
hits: 3
tags: [memex, wikis, message-boards, knowledge-management, information-architecture, scalability, essay]
---

> *Memex architecture essay — preserved from this reference instance's earlier development as the Memex about the Memex. Not a working thread for the active project; historical thinking about the architecture itself.*

# Knowledge Systems Comparison

## Summary

Comparing message boards, wikis, and the Memex as knowledge management architectures. The key axis is their relationship to time: message boards are chronological (slaves to it), wikis are revisionary (fight it to stay current), and the Memex is lifecycle-driven (rides momentum and decay). A secondary axis is social vs. personal — boards and wikis are natively social tools; the Memex is natively personal, which changes what "linking" means from topical relatedness to associative continuity.

## Detail

**Message boards**: Organized by time. Atomic unit is a post. Append-only, many-to-many. Failure mode is burial — good information sinks under new activity. Discovery by browsing or search.

**Wikis**: Organized by topic. Atomic unit is a page. Revised in place to maintain canonical current state. Failure mode is staleness or inconsistency. Discovery by link-following or search.

**Memex**: Organized by associative momentum. Atomic unit is a thread. Threads have a lifecycle — promoted, compressed, split, demoted based on activity. Failure mode is losing a train of thought. Discovery by entering any node and following cross-references (the graph is the index).

**Linking semantics**: In a wiki, a link says "this topic relates to that topic." In the Memex, a link says "these two trains of thought touched, and you might want to follow one from the other."

## Scale Analysis: 5,000 Threads

**What scales:** The tiered cache model (active/threads/artifacts) keeps the always-loaded budget at 400 lines regardless of total thread count. Compression lifecycle prevents hot-tier bloat.

**What breaks:**

- **Graph navigability degrades.** Watts-Strogatz 3-hop property requires deliberate shortcut links maintained through every demotion/split/rotation. Currently maintained by agent diligence — no automated verification. At scale, cross-reference preservation on every structural change becomes an O(n) audit.
- **Discovery of forgotten threads.** A demoted thread whose only inbound link was compressed or split is effectively orphaned. "The graph is the index" silently fails; in practice, recovery falls back to grep.
- **Cross-reference maintenance cost.** ~3–5 outbound links per thread × 5,000 = 15,000–25,000 links. Every rename, split, or demotion is a potential breakage. The enforcer can report but not fix.
- **Narrow active window.** 5–8 active threads forces artificial rotation when genuine active interests exceed that count.

**Missing tooling the architecture needs:**

1. **Tag index / faceted lookup** — tags exist in frontmatter but nothing aggregates them. A secondary graph, not a hierarchy.
2. **Backlink index** — generated, not hand-maintained. Answers "what links to this thread?" without loading everything.
3. **Orphan detection** — flag threads with zero inbound links (invisible to graph navigation).
4. **Connectivity verification** — script that walks the graph and reports unreachable nodes or single-bridge clusters against the 3-hop invariant.

**Bottom line:** Tiering scales. Graph navigation doesn't — not without tooling. The constitution states invariants it doesn't provide mechanisms to enforce.

## Codex Scaling Report Assessment (2026-03-17)

Codex produced [2026-03-17-scaling-approach.md](../../reports/2026-03-17-scaling-approach.md). Core framing is correct: this is a graph operations problem, not a storage problem. Recommended sequence (measure → generate indexes → automate) is disciplined.

**Where the report is strong:**

- Correctly identifies graph maintenance as the failure point, not storage or prompt budget.
- Sequence is right: observability before automation, candidate changes before silent edits.
- "Crawler as candidate-change producer" is the right trust model for early automation.

**Where the report is thin:**

1. **Doesn't audit existing tooling.** `memex-lint.sh` already covers budget compliance, thread sizes, frontmatter, cross-references, and orphan detection. Step 1 ("make graph health measurable") may partially exist. The report should have checked what the lint script actually reports before proposing new tooling.
2. **Indexes described but not specified.** Backlink and tag indexes — what format? Generated files, in-memory at session open, appended to threads? This matters because the Memex has a "no central index" principle. Generated indexes must be positioned as recovery tools, not primary navigation, or the graph will rot behind them.
3. **No cost model.** Running a model against the full thread directory at 5,000 threads — how often, at what token cost? Backlinks, orphans, and connectivity are deterministic (no model needed). The model is only required for semantic checks ("these two threads should be linked"). The report conflates the two.
4. **Active-window reassessment is deferred without criteria.** Correct to defer, but what metric from graph reports would trigger a change? What evidence says "8 is too few"?

**Recommended sequence (revised):**

1. **Audit `memex-lint.sh` coverage** — fill gaps (backlinks, connectivity, single-bridge detection) in the existing script rather than building a new tool.
2. **Generate backlink index as an enforcer report artifact** — not loaded by default, consulted on demand. Respects "no central index."
3. **Connectivity report as enforcer output** — makes the 3-hop invariant testable.
4. **Crawler = lint + diff** — first version just runs the lint, flags what changed since last run. Semantic checks come later.

## Connections

→ [constitution.md](../../constitution.md) — defines the Memex's navigability constraint (Watts-Strogatz small-world) and compression lifecycle that distinguish it from static wiki pages
→ [tooling-roadmap.md](../reference-notes/tooling-roadmap.md) — tracks planned scripts and background operators including Crawler and Spider
→ [2026-03-17-scaling-approach.md](../../reports/2026-03-17-scaling-approach.md) — Codex scaling report assessed in this thread

## Open Questions

- Where do tools like Notion, Roam, or Zettelkasten fit on these axes?
- Is there a hybrid that captures the social benefits of boards/wikis while preserving personal continuity?
- How does the Memex's "capture bias" compare to wiki notability standards or forum posting norms?
- What does `memex-lint.sh` already cover, and what gaps remain for backlinks and connectivity?
- What metric from graph health reports would justify expanding the active-thread window beyond 5–8?
- Should generated indexes be files (auditable, diffable) or ephemeral session-open outputs?
