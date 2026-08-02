# Blueprints

Blueprints explain major Gator features at a human/architecture level.

They sit between:

- charters, which describe module ownership and invariants
- code, which implements the feature

Use these pages when the question is:

- "How does this feature work end to end?"
- "What is implemented versus partial?"
- "Which modules participate?"
- "Where are the known fragile areas?"

Current pages:

- [Repo Topology](repo-topology.md) — how gator-command, the public clone, and fleet repos relate
- [Hook Pipeline](hook-pipeline.md) — how pre-commit/post-commit hooks work across all three repo types
- [Thread Lifecycle](thread-lifecycle.md) — when threads are created, updated, and rotated between tiers
- [Commit Pipeline](commit-pipeline.md) — end-to-end commit flow
- [Charter Verify](charter-verify.md) — charter validation system
- [Session Intelligence](session-intelligence.md) — session extraction, storage, dashboard display, and gaps
- [Session Block Capture](session-block-capture.md) — commit-scoped transcript slices, CLI-first on-demand capture
- [Install And Upgrade](install-and-upgrade.md) — gatorize, clone gap, hook self-heal, and update flow
