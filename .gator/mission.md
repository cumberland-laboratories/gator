# Mission

## What We're Building

**Gator** — the Git-native governance layer for AI-assisted engineering. Not a coding framework. Not a SaaS audit tool. The semantic layer that turns AI coding activity into governed, inspectable, auditable evidence — living in Git, traveling with every repo, queryable at fleet scale.

Gator plays well with whatever AI coding framework a team already uses — Claude Code, Codex, Cursor, Spec Kit, Gemini CLI. Those tools answer "how do I code effectively with AI." Gator answers "how do I govern AI coding in Git." They compose. Gator does not compete.

## The Strategic Insight

**The charter is the key.**

When an AI agent builds a charter before touching code, two things happen:

1. The agent's understanding of the module — its functions, its callers, its invariants, its tripwires — becomes a committed artifact in Git.
2. Every subsequent code change can be verified against that understanding: did the agent preserve what it said it would? Did a human review and correct the map before the change happened?

Without charters, Git governance is surface-level: you know what files changed. With charters, you know what the agent *understood* it was changing — and whether that understanding was accurate and human-verified.

This is the semantic layer enterprise AI governance has never had. Not "did an AI generate this commit?" but "can you prove the AI understood the module, and did a human verify that understanding before the change?"

That proof lives in Git. It travels with every repo. It requires no proprietary infrastructure.

## Why Charters Enable Everything Else

The charter is not a refactoring tool. Efficient refactoring is a proof mechanism — a way to demonstrate that the charter model works. The real value is:

- **Audit trail**: every code change linked to a documented understanding of what was changing and why
- **Compliance evidence**: Article 14 (human oversight of AI-generated code) satisfied by the charter review cycle, not by bolted-on attestation
- **Blast radius mapping**: before a change, not after — what would break, what must not change
- **Fleet-scale queryability**: charter coverage, tripwire inventory, drift detection — all from git log and file state, no custom service
- **Framework-agnostic**: the charter is the handshake between whatever AI coding tool generated the code and the governance record

## What Gator Is Not

Gator is not an AI coding framework. It does not help agents write better code. It governs the process by which AI agents write and change code — and makes that governance legible to humans, auditable by machines, and portable in Git.

Gator does not compete with Claude Code, Codex, Cursor, Spec Kit, or any skills/constitution layer. It lives above them, in Git.

## The Long Horizon

Deep AI-coding governance in Git. Full steam ahead, even if it takes months.

The end state: Git refs, artifacts, and trailers as the governance state machine — not just code history. Versioned governance releases that fleet repos can compare themselves against. Governed pipeline seams where every model-to-model handoff is a committed artifact with a defined role and verification rule. Signed approvals. Server-side enforcement. Fleet-level analytics over the governance record every repo already carries.

The market gap: every competitor either bolts governance onto hosted infrastructure (which breaks air-gap and local-first requirements) or treats Git as a storage layer rather than the control plane. Gator is built the other way around — Git is the architecture, not the backend.

## Scope Boundaries

**In scope:**
- Charter layer — the semantic bridge between AI coding and Git governance
- Pre-commit enforcement — deterministic, local, fast, tamper-evident
- Fleet visibility — status, drift, session archaeology, audit — all from git + file state
- Policy propagation — org constitution and standards distributed via thin-link at session speed
- Governance release channel — versioned governance updates, fleet-safe rollout
- Pipeline seam governance — model-to-model handoffs as committed artifacts
- Integration recipes — Gator composing with AI coding frameworks, not replacing them

**Out of scope:**
- Hosted SaaS dashboards (later tier)
- SOC2/HIPAA certification of Gator itself (later)
- CI/CD integrations (later)
- SSO/SAML (later)

## What Success Looks Like

- An engineering org can prove, from git history alone, that every AI-generated code change was preceded by a documented understanding of the module and a human review of that understanding
- A policy change at the command post propagates to every fleet repo at next session start
- A fleet audit answers "which repos are stale, which charters drifted, what's off-roadmap" in seconds, from local git state
- Any AI coding framework a team uses composes cleanly with Gator — the governance layer is invisible until it matters
- The whole thing is git repos, markdown, and Python — no proprietary infrastructure required

## Connections

→ [Roadmap](roadmap.md) — prioritized build sequence
→ [Git-Native Gator Leverage](artifacts/2026-06-06-git-native-gator-leverage.md) — strategic artifact: governance release channel, pipeline seams, deep Git primitives
→ [Charter Positioning](artifacts/2026-06-06-charter-as-governance-key.md) — strategic artifact: why the charter is the architectural foundation
