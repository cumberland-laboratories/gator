---
date: 2026-10-25
type: specification
issue: 75
related: [76, 34, 35]
supersedes: "sketch of loop charter-and-dangerous-pattern-policy-2026-10-25T00-20-56Z, section 'Override lifecycle' (charter integrity is not an override candidate) and the 'Charter integrity' row of its policy table"
status: Architect decision 2026-10-25
---

# Pre-commit resolution contract (#75, corrected)

## Decision

The default pre-commit policy has three outcomes. This table is the contract:

| Finding | Default behavior | Resolution | Evidence |
|---|---|---|---|
| Charter requirement (`charter-alongside-code`, `charter-index-gap`, `cross-cutting-missing`) | Block | The agent updates the charter. When no charter edit is warranted, the Architect may approve the exact staged change (`gator hook approve`; later the #76 Commits button). The agent never approves. | `Gator-Charter-Changed: override-skip` and `Gator-Override-*` trailers |
| Dangerous pattern (HIGH/CRITICAL Layer 1 lint) | Warn | The agent presents the finding; the Architect decides to fix, remove, or keep it. A keep decision is recorded as session acknowledgement, which is separate from any override. | Optional `Gator-Dangerous-Patterns` / `-Acknowledged-By` trailers |
| Invalid draft or other correctness failure (`frontmatter-parse`, `invalid-change-type`, `invalid-significance`, `empty-commit-draft`, `missing-message`, `legacy-override-file`, `unmerged-index`, `legacy-override-record`, `invalid-dangerous-pattern-acknowledgement`) | Block | Fix and retry. It cannot be overridden. | None |

Mode exceptions are unchanged. Enterprise `evidence_only` makes a dangerous pattern block as an external approval. The legacy `warn` and `off` levels keep their broad behavior.

## Why the sketch was corrected

The approved sketch removed the charter override, on the reasoning that charter integrity should not look equivalent to a lint false positive. In practice the charter check has edge cases: misrouted INDEX rows, false coverage gaps (#16, #17, #18, #88), and changes too small to describe. Without an escape hatch, these cases leave only token charter edits or the blunt legacy `warn` level. Removing the hatch also left nothing approvable in a normal repository, so the planned Commits approval button (#76) had no default use. The Architect decided to restore the Architect-only, tree-bound approval for charter rules, and to keep dangerous patterns as warnings.

## Invariants

- Only the explicit resolution map makes a rule approvable: `precommit_policy.charter_resolutions()` for charter rules, and `resolution_map()` for lint in an external-approval mode. Every other rule is fix-required.
- An acknowledgement never creates, uses, or retires an approval. An approval never acknowledges a dangerous pattern. A commit with both kinds of finding records only the charter rule as overridden.
- Approvals written by this runtime carry `resolution_policy`. The legacy-record guard treats only unmarked same-tree approvals as leftovers from an earlier runtime.

## Provenance

- Planning loop: `charter-and-dangerous-pattern-policy-2026-10-25T00-20-56Z` (plan approved after three rounds).
- Coding loop: `charter-and-dangerous-pattern-policy-2026-10-25T00-37-09Z` (four checkpoints approved; committed as `89707a2`).
- This correction: one follow-up commit, with Codex's review of the staged patch (10 focused tests passed). That review asked for this contract, a combined charter-plus-warning regression (`test_charter_approval_with_a_dangerous_warning`), and stale-description cleanup.
