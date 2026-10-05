# Review: Revision Planning from Approved Plans and Architect-Supplied Coding Plans (#51)

## Executive Summary

- **Verdict:** APPROVE. The plan is implementation-ready and preserves the requested distinction between reviewed plans and Architect-supplied plans.
- **Provenance:** revision planning captures two fixed, digest-verified baseline artifacts in a new planning loop; it never mutates or revives the source loop.
- **Trust boundary:** Architect plan files use one containment, reparse/symlink, text, size, and single-read validation path before creation, then are copied under a neutral fixed name.
- **Verification:** atomic-failure, positional-binding, legacy-compatibility, dashboard, and document-drift tests cover the principal risks.

## Verdict

APPROVE — the plan is ready to implement as written.

It defines the additive schema, fixed artifact names, lock ordering, creation grammar, strict status projections, and UI labels needed to keep the two source kinds unambiguous.

## Findings

No revision findings.

## Scope Check

The plan implements both sketch scopes and respects the exclusions. Revision planning remains a new ordinary planning loop, with copied source evidence as its sole authoritative baseline. Coding from an Architect plan is explicitly distinct from the existing approved-planning-loop path and preserves normal staged-tree review and commit handoff.

The plan's `## Context Checked` is credible. It names the applicable Loop, Dashboard Server, Dashboard UI, and Cross-Cutting charters; the charter index; the host, session, submit, CLI, Dashboard server, and browser sources; and the document pair. Spot checks confirm the existing guarded coding-source order, fixed-name brief verification, strict Dashboard projections, and stable artifact/revision behavior it extends.

## What Looks Good

- Fixed-name verification and status views avoid trusting artifact names or paths stored in session metadata.
- The source-lock/start-lock ordering and rollback plan preserve atomic creation and source-loop immutability.
- The `coding.source_kind` normalization gives legacy coding sessions a defined compatibility path and makes malformed values visible as integrity failures.
- The plan keeps source briefs and earlier source residue non-default, so the new sketch and its own Context Checked retain their intended authority.
- It treats the protocol, artifact-format, and join-command pairs as a synchronized contract and tests the drift boundary.
