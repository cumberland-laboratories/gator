---
last-touched: 2026-05-17
tags: [governance, charters, failure-modes, navigation-coding]
---

# Failure Modes and Self-Correction

## Summary

A common objection to charters is that a stale charter could become a confidently wrong map. In practice, that is not the dominant failure mode. The more typical pattern is that the charter gives the agent an expectation about the code, and the code immediately confirms or violates that expectation. When the map is even moderately viable, disagreement tends to surface as visible confusion rather than silent corruption.

Put differently: the charter is not ground truth. It is a structured hypothesis about the codebase. Its value is twofold:

- if the charter and code agree, orientation is faster
- if the charter and code disagree, the discrepancy becomes visible early

This makes charters useful not only as retained memory, but as cross-check surfaces.

## Why This Does Not Behave Like Static Docs

Static architecture docs mostly inform. A navigation-coded charter loop does two jobs:

- it informs the next change
- it exposes drift when the documented expectation no longer matches the code

That is why the recursive maintenance loop matters so much. The system is not "documentation plus code." It is code, map, and discrepancy detection operating together.

## Typical Failure Pattern

The feared pattern is:

1. Charter is stale
2. Agent trusts it blindly
3. Agent makes bad code changes
4. Bad map causes more bad work

The empirically more common pattern is:

1. Charter is stale
2. Agent reads it and forms an expectation
3. The code does not match the expected structure
4. The agent stops, asks, or updates the map

An example shape is: "the charter says `write_file()` should exist here; where is it?" The mismatch becomes the signal.

## What Makes This Work

This self-correcting behavior depends on a few conditions:

- the charter is close enough to reality to create useful expectations
- the agent still reads the code rather than treating the charter as an oracle
- disagreement is treated as a reason to inspect, not to push through

If those conditions hold, both the charter and the code do not need to be perfect. They only need to be different enough that drift is detectable.

## The Better Counterfactual

This also answers part of the "why not just write `ARCHITECTURE.md` and module `README`s?" objection.

The issue is not only that static docs go stale. It is that they usually do not participate in a loop where:

- they are consulted before edits
- they are updated as part of the same operation
- their mismatch with code is operationally useful

Navigation coding gets much of its value from that loop, not only from having written things down.

## Connections

→ [What Gator Requires From a Model](what-gator-requires-from-a-model.md) — assumes the agent reads before acting and checks repo artifacts against code
→ [Why Navigation Coding Feels Different](why-navigation-coding-feels-different.md) — explains the friction of resolving ambiguity before coding
→ [Supporting Research](supporting-research.md) — evidence for structured navigation, independent review, and compression
