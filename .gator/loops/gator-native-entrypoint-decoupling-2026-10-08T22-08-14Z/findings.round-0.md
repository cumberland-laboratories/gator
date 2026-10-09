# Review: Gator-Native Repository Entry Point and Optional Agent Adapters

## Executive Summary

- **Verdict:** REVISE, for one documentation-completeness issue.
- The bootstrap, installer/update, state-boundary, compatibility, and test strategy are specific and stay within the approved migration scope.
- The proposed removal of default native-file ownership is not matched by a complete audit of shipped documentation that currently describes those files as Gator-managed or as the required primary entry point.
- Expand the adoption checkpoint into an inventory-driven update (with a regression guard) so the released guidance does not contradict the new contract.

## Verdict

REVISE

The implementation plan is otherwise ready in its technical approach, but its documentation change set must cover all shipped statements of the retired ownership model before the plan can be approved.

## Findings

### Finding 1: Documentation inventory is incomplete for the new ownership boundary

**Severity**: Medium

**Location**: Change 9, "Documentation and adoption," and coding checkpoint 4.

**Issue**: The listed documentation files omit shipped surfaces that currently state that `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` are Gator's managed or primary entry point. For example, `.gator/.includes/procedures/enforcer-review.md` says `AGENTS.md` and `CLAUDE.md` define the primary-agent entrypoint, and `.gator/.includes/reference-notes/enforcer-configuration.md` makes the same role-boundary claim. These statements contradict the planned explicit `gator init` -> `GATOR_INIT.md` contract even though the files are not installer/update documentation. Similar stale wording can remain in other shipped reference notes unless the update is inventory-driven rather than a named partial list.

**Suggestion**: Add a documented audit of all shipped template, dogfood, README, and user-documentation references to `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, managed blocks, entry points, rollback/pre-update backups, and native-file ownership. Classify each hit as historical/research material to preserve or behavior guidance to revise. Explicitly revise the enforcer procedure/configuration surfaces above so they describe vendor files as optional repository-owned context and direct Gator session startup to `gator init` / the bootstrap. Add a focused regression test or source-inventory assertion that disallows retired behavioral claims in the maintained onboarding/procedure/reference surfaces, while allowing clearly historical CHANGELOG/research references.

## Scope Check

The plan remains within the sketch: it chooses the recommended first delivery, makes the migration additive within `.gator/`, preserves historical native files byte-for-byte, and defers adapters. `## Context Checked` is credible: it names the required charters, relevant package/template paths, the sketch, and the loop protocol. The four coding checkpoints are responsibility-based, sequenced, and independently verifiable. Finding 1 requires completing checkpoint 4; it does not expand product scope.

## What Looks Good

- The resolver-based placement and legacy `gator init` fallback preserve layout compatibility without writing during session open.
- The update JSON compatibility decision is explicit rather than silently removing a public field.
- The native-file byte-preservation cases and no-write `gator state repair` compatibility path directly test the migration's most important safety property.
