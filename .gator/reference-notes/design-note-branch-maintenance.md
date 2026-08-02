# Design Note: Branch-Based Maintenance

## The Pattern

Borrowed from Signal's nightly shelf updates. Isolate expensive mutation work on a git branch. Merge back after review.

## How It Works

1. **Branch** — `git checkout -b maintenance/YYYY-MM-DD` from `dev`
2. **Background agents work the copy** — fix broken links, retag, resize threads, update cross-references, run wiki pipeline, run enforcer audit. Agents can be aggressive; mistakes never touch the live Memex.
3. **PR to `dev`** — human (or primary agent) reviews the diff. Every change is visible, auditable.
4. **Merge** — clean, reversible, git history preserved.

## Why This Matters

- **No contention** with the live Memex during maintenance. The primary agent and human can keep conversing on `dev` while background agents work the branch.
- **Resolves the enforcer write boundary** more elegantly. Instead of "enforcer must never edit," it becomes "enforcer edits a copy, human authorizes the merge." Same safety, more utility — the enforcer can actually fix what it finds.
- **Git gives isolation, diffing, rollback, and audit trail for free.** No custom tooling needed.
- **Proven pattern** — Signal's nightly shelf updates use the same shape for question bank maintenance.

## When to Implement

When background maintenance (design-note-background-maintenance.md) reaches the point where multiple agents need write access concurrently, or when enforcer fixes are frequent enough that report → manual-fix is too slow.

## Relationship to Other Patterns

- Extends: background subagent pattern (reads → writes, but on a branch)
- Extends: enforcer read-only boundary (from "can't write" to "writes to a copy, merge gated by human")
- Borrows from: Signal nightly shelf updates (snapshot → mutate → merge)
