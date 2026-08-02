---
last-touched: 2026-05-16
tags: [architecture, sizing, context, doctrine]
---

# Charter Sizing — Active Context vs. Total Pool

## Summary

The useful interpretation of the old "2%" idea is **not** "2% of the codebase" and **not** "2% of the total charter corpus." It is a heuristic for the **active charter working set per task**: the subset of charters an agent loads alongside the code it is changing. The total charter pool can be materially larger as long as `INDEX.md`, cross-references, and charter boundaries keep the per-task load small.

This matches the observed production pattern. A repo can sustain a substantial charter corpus on disk and still work well because the agent does not read the whole corpus at once. It navigates to the relevant subset. The governing question is not "how big is the whole map?" but "can the agent load the relevant map fragment comfortably beside the code under change?"

## Connections

→ [Charter Format](../charters/README.md#sizing) — sizing guidance for charter authors
→ [Supporting Research](../../docs/supporting-research.md) — evidence for structured navigation over raw exploration
