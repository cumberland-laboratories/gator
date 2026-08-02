# Architecture

## Design Principle

Git is the infrastructure. Commit hashes are tamper evidence. `git log` is the audit trail. `git pull` is the sync mechanism. Gator adds a structured governance layer on top of what git already provides — no databases, no hosted services, no proprietary formats.

## Repo Layout

A governed project repo (after `gator gatorize .`):

```
your-project/
  .gator/                      ← governance layer
    constitution.md            ← rules for AI agents
    charters/                  ← structured code maps
      INDEX.md                 ← charter routing table
      cross-cutting.md         ← multi-module invariants
      module-name.md           ← per-module charter
    scripts/
      hooks/                   ← pre-commit, commit-msg, post-commit
      gator-init.py            ← boot sequence
      gator_core.py            ← shared infrastructure
    pulse.md                   ← strategic operations brief
    mission.md                 ← what you're building
    roadmap.md                 ← priorities
    inbox.md                   ← capture buffer
    status.json                ← machine-readable governance state
    whiteboard.md              ← hook findings
  CLAUDE.md                    ← Claude Code entry point
  AGENTS.md                    ← Codex entry point
  GEMINI.md                    ← Gemini entry point
```

## Data Flow

```
  Constitution (rules)
       │
       ▼
  AI Agent (reads rules, reads + writes charters, writes code)
       │
       ▼
  git commit
       │
       ▼
  Pre-commit hook (deterministic validation)
       │
       ├── PASS → trailers assembled, status.json updated,
       │          session log entry appended
       │
       └── BLOCK → findings to whiteboard.md,
                   commit rejected with explanation
```

## Trust Boundaries

1. **The pre-commit hook is deterministic.** No LLM, no interpretation. Same input produces same output every time. The agent cannot influence the hook's decision.

2. **The enforcer is a different model.** Cross-model review means different training, different blind spots. Same-model review is not enforcement.

3. **Trailers travel with commit history.** Changing a trailer changes the commit hash, providing integrity within a verified chain. However, this is tamper-evident within git's own trust model — a force-push or history rewrite can remove evidence. For cryptographic audit guarantees, add signed commits (GPG/SSH) with keys held outside the agent's authority, plus branch protection to prevent force-push. Gator provides the governance metadata; your git hosting platform provides the integrity enforcement.

**Honest scope:** The current gate is behavioral, not cryptographic. Gator creates friction, visibility, and audit trails that make governed work the path of least resistance. It does not prevent a determined adversary with repo write access from bypassing controls. See → [Threat Model](threat-model.md) for what each layer protects against.

## Separation of Concerns

In each governed repo:

| Layer | Contains | Updated by |
|-------|----------|-----------|
| `.gator/` | Governance layer — constitution, charters, hooks, knowledge base | `gator gatorize .` refreshes templates/scripts; user owns charters and knowledge files |
| Your code | Source code, tests, configs | You and your AI coding agents |

Templates and scripts refresh on upgrade. Your charters, knowledge base, and project content are never overwritten.

## Multi-Model Architecture

The constitutions and charters are the interface contract. Any model that can read markdown and follow instructions can operate the system:

- **Claude Code** reads `CLAUDE.md` → constitution → charters
- **Codex CLI** reads `AGENTS.md` → same constitution → same charters
- **Gemini CLI** reads `GEMINI.md` → same constitution → same charters

The governance layer is the constant. The AI model is the variable.
