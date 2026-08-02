# Gator

**AI-assisted engineering governance — local-first, git-native, model-neutral.**

Gator is a governance layer for AI-assisted software development. It enforces coding standards at commit time, maintains structured knowledge across sessions, and provides fleet-wide visibility across repos — all using git and markdown. No hosted services, no vendor lock-in.

---

## What Gator Does

- **Charter-alongside-code enforcement** — the AI agent creates and maintains structured module maps (charters); a pre-commit hook blocks commits where code changed but the agent didn't update the charter
- **Cross-model working** — Claude Code, Codex CLI, Gemini CLI, and Cursor all read the same governance layer
- **Cross-model enforcement** — the [enforcer pattern](enforcer-patterns.md) uses a different AI model to review the coding agent's work, ensuring independent oversight
- **Session continuity** — mission, roadmap, threads, and session history persist in the repo across sessions and models
- **Fleet governance** — one command post governs multiple repos with shared policy, drift detection, and audit
- **Session archaeology** — structured audit records extracted from AI coding sessions across vendors

## Quick Install

```bash
# Clone Gator
git clone https://github.com/cumberland-laboratories/gator.git
cd gator

# Gatorize any git repo
bash gator-engine/scripts/gatorize.sh /path/to/your/repo
```

Open the governed repo in your AI coding tool. The agent reads the constitution and starts working within the governance loop. Your first `git commit` fires the hooks.

[Full getting started guide](getting-started.md){ .md-button .md-button--primary }

## Who It's For

| Audience | Start here |
|----------|-----------|
| **Engineers** using AI coding tools | [For Engineers](for-engineers.md) |
| **Engineering Directors** managing AI adoption across teams | [For Directors](for-directors.md) |
| **Leadership** evaluating governance and compliance | [For Leadership](for-leadership.md) |

## Deep Dives

| Topic | What it covers |
|-------|---------------|
| [What Is Navigation Coding?](what-is-navigation-coding.md) | The defining essay — why comprehension is the bottleneck, ecosystem convergence, the closed loop |
| [Why Navigation Coding Feels Different](why-navigation-coding-feels-different.md) | The experiential shift from prompting to governed collaboration |
| [Origin Story](origin-story.md) | How the pattern emerged from practice — vibe coding drift, the refactor break, constitutional architecture |
| [Enforcer Patterns](enforcer-patterns.md) | Cross-model review — deployment patterns, model pairing, the high-supervision philosophy |
| [What Gator Requires From a Model](what-gator-requires-from-a-model.md) | Minimum behavioral assumptions, failure modes, why instruction topology beats prompt size |
| [Supporting Research](supporting-research.md) | Academic and vendor evidence — 21 cited sources across six pillars |

## Flows

| Flow | When to use |
|------|------------|
| [Refactor a Codebase](refactor-with-gator.md) | You have existing code and want to restructure it with AI governance |
| [Build a New Project](new-project-with-gator.md) | You're starting from scratch and want governance from day one |
| [Gatorize an Existing Repo](getting-started.md) | You have a git repo and want to add governance |
| [Fleet Governance](fleet-governance.md) | You have multiple repos and want centralized oversight |
| [Compliance & Audit](audit-compliance.md) | You need evidence for regulatory or procurement review |

## Reference

| Document | What it covers |
|----------|---------------|
| [Getting Started](getting-started.md) | Installation and first session |
| [Installation](installation.md) | Platform-specific install guidance |
| [Architecture](architecture.md) | System design and trust boundaries |
| [Governance Model](governance-model.md) | Constitution, charters, and pre-commit enforcement |
| [Fleet Governance](fleet-governance.md) | Command post, policy propagation, drift detection |
| [Audit & Compliance](audit-compliance.md) | Evidence streams, regulatory alignment |
| [Session Archaeology](session-archaeology.md) | Cross-vendor session extraction and audit trails |
| [Command Reference](command-reference.md) | CLI commands and scripts |
| [Upgrade](upgrade.md) | Updating Gator across repos |
| [Gator Charter Schema v1](charter-schema-v1.md) | Official public schema for charter artifacts |
| [Charter Formation Process](charter-formation-process.md) | Official public process for creating a charter set from a fresh codebase |
| [Blueprints](../blueprints/README.md) | Human-readable end-to-end feature pages |
| [Commit Pipeline](../blueprints/commit-pipeline.md) | Pre-commit, trailers, cleanup, overrides, and hook surfaces |
| [Charter Verify](../blueprints/charter-verify.md) | Structural charter-vs-code verification and how it feeds review |

## Version

Current release: **v1.0.0**

---

*[Cumberland Laboratories](https://github.com/cumberland-laboratories)*
