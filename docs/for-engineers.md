# Gator for Engineers

**Gator gives you a disciplined AI coding loop that preserves speed without losing architectural accountability.**

---

## The Problem

You're shipping fast with AI coding tools. But three things keep happening:

1. **Context evaporates between sessions.** You solved a hard problem last Tuesday. Today the AI has no memory of it — or worse, it confidently re-introduces the bug you fixed.
2. **Code outpaces understanding.** AI generates correct code that nobody can explain. The repo grows but the reasoning surface doesn't. Six months later, you're afraid to touch it.
3. **Governance feels like friction.** Documentation, code review, standards compliance — they slow you down, so you skip them. Then something breaks and there's no trail.

Gator solves all three without slowing you down. The governance happens *at commit time*, not as a separate ceremony. The context persists *in the repo*, not in a tool-specific memory that disappears when you switch models.

---

## What Gator Does For You

### Charters: The Comprehension Layer

Charters are structured maps of your code modules — what each function does, who calls it, what models it touches, and where the non-obvious behavior lives. **The AI agent creates and maintains charters, not the human.** When the agent reads your code, it writes the charter. When the agent changes code, it updates the charter. The human reviews charters periodically for accuracy, but authorship is the agent's job:

```
### apply_grade(submission, raw_score, grader)
File: core/utils/grading.py
Creates Grade record with penalty-adjusted score.
Models: Submission(R), Grade(W), Enrollment(RW)
← grade_submission() in views_assignments
→ see cross_cutting.md "Late Penalty Timing"
! The instructor sees raw_score, but Grade.score
  is penalty-adjusted. These are different numbers.
```

The `!` marks non-obvious behavior (tripwires). The `←` and `→` trace dependencies. Access patterns (`R`/`W`/`RW`) predict side effects without reading the function body.

When the AI agent changes code, it updates the charter alongside. You never write charters by hand — the agent authors them from the code, and the pre-commit hook enforces that they stay current. Your role is to review what the agent wrote and correct it when it's wrong.

→ *Detail: [Governance Model](governance-model.md)*

### Pre-Commit Enforcement: Governance at Commit Time

A deterministic pre-commit hook fires on every `git commit`:

- **Charter-alongside-code** — if code files changed but no charter was updated, the commit is blocked. No exceptions unless you explicitly override (and the override is audited).
- **Structured metadata** — the hook reads your session's commit draft and assembles `Gator-*` trailers: change type, significance, decision tags, charter status, agent identity.
- **Whiteboard findings** — if something looks wrong (dangerous code patterns, missing governance signals), findings go to `.gator/whiteboard.md`. You see them immediately.

This is structural enforcement, not a suggestion. The hook is a separate process — its decision is deterministic and outside the agent's prompt loop. A blocked commit produces a STOP box that spikes the agent's attention and is designed to cause the agent to pause and present findings to the Architect rather than self-approving.

→ *Detail: [Governance Model](governance-model.md)*

### Cross-Model Working

Gator is model-neutral. The governance layer is markdown files in `.gator/`. Any AI tool that reads files can follow it:

| Tool | Entry Point | How it works |
|------|------------|--------------|
| Claude Code | `CLAUDE.md` | Reads constitution, charters, threads at session open |
| Codex CLI | `AGENTS.md` | Same governance, same enforcement |
| Gemini CLI | `GEMINI.md` | Same governance, same enforcement |
| Cursor | `CLAUDE.md` | Reads governance (no hook integration yet) |

Switch models mid-project without losing context. Hand a review to a different model than the one that wrote the code — the governance layer carries the state, not the tool's memory.

### The Review Wall

The enforcer (code reviewer) is always a different model than the coding agent. This is by design:

- Coding agent writes code, updates charters, prepares commit
- Pre-commit hook validates (deterministic, no LLM)
- Enforcer model reviews findings from a different trust boundary

Same-model review is not enforcement. The wall between coding and reviewing is the feature.

→ *Detail: [Enforcer Patterns](enforcer-patterns.md) — deployment options, model pairing guide, and the high-supervision philosophy*

### Session Continuity

Your working context persists in the repo, not in tool-specific memory:

- **Mission + roadmap** — what you're building and what's next. Loaded at every session open.
- **Active threads** — current topics, design decisions in progress, open questions.
- **Inbox** — zero-friction capture for ideas that aren't threads yet.
- **Commit draft** — structured session log that becomes the commit message source.
- **Session logs** — rolling activity logs appended on every commit. Committed summaries generated on demand via `gator sessions commit-summaries` for durable audit evidence.

When you start a new session (same model or different), the agent reads these and picks up where you left off. No "catch me up" needed.

→ *Detail: [Session Archaeology](session-archaeology.md)*

### Session Archaeology

Gator extracts structured audit records from your AI coding sessions:

- **Claude Code** — reads from `~/.claude/`
- **Codex CLI** — reads from `~/.codex/`
- **Gemini CLI** — reads from `~/.gemini/`

Extraction produces standardized summaries: decisions made, files changed, session duration, agent identity. These get committed to `.gator/sessions/` as git-tracked markdown — your personal audit trail across tools and sessions.

You'll never lose track of "what did I decide last week and why?"

→ *Detail: [Session Archaeology](session-archaeology.md)*

---

## What It Looks Like in Practice

### A Normal Commit

```
$ git commit

  gator pre-commit: PASS

  ✓ charter-alongside-code: code changed, charter updated
  ✓ commit-draft: frontmatter present, significance: notable
  ✓ dangerous-code-lint: no findings

  Trailers assembled:
    Gator-Charters: 3
    Gator-Functions: 12
    Gator-Charter-Changed: yes
    Gator-Significance: notable
    Gator-Change-Type: feature
```

### A Blocked Commit

```
$ git commit

  gator pre-commit: BLOCKED

  ✗ charter-alongside-code: Code files changed
    (src/auth.py, src/tokens.py) but no charter was updated.
    Stage a charter update and retry.

  Findings written to .gator/whiteboard.md

  ┌─────────────────────────────────────────────────────────┐
  │ STOP. Do not override this yourself.                   │
  │                                                        │
  │ Present these findings to the Architect.                │
  │ The Architect decides:                                 │
  │   1. Update the charter and retry the commit           │
  │   2. Approve override:                                 │
  │      python .gator/scripts/gator-approve.py            │
  │                                                        │
  │ You may NOT create override files yourself.            │
  │ You may NOT run gator-approve.py yourself.             │
  │ Unauthorized self-approval is a governance violation.  │
  └─────────────────────────────────────────────────────────┘

  Block ID: a554c101
```

### Fleet Status (if your team uses a command post)

```
$ gator fleet-report

  ✓ service-api
    gen 2  |  charters: 4 (23 fn)  |  hooks: yes
    trailers: sig: notable | type: feature | charter: yes

  ✓ frontend
    gen 2  |  charters: 2 (8 fn)  |  hooks: yes

  ! data-pipeline
    gen 1  |  charters: 0  |  hooks: no
    ⚠ Generation drift. Run gator update.
```

---

## What's Coming

| Feature | What it means for you | Timeline |
|---------|----------------------|----------|
| Install polish | `gator-preflight.sh` checks your system, `gator-setup.sh` does the full onboarding | Weeks 5-7 |
| MCP server | Gator tools available natively in Claude Code sessions — charter lookup, fleet status, search | 3-4 weeks |
| Explicit session lifecycle | Better continuity for long sessions (no more 4-hour timeout) | Phase 3 |
| `gator review` | Structured handoff between coding and reviewing models with full context packet | Phase 3 |
| Integration recipes | "Using Gator alongside Spec Kit" and others — Gator complements your stack | 5-6 weeks |

---

## Getting Started

### Prerequisites

- Git 2.30+
- Python 3.10+
- An AI coding tool (Claude Code, Codex CLI, Gemini CLI, or Cursor)
- Bash (native on macOS/Linux; Git Bash on Windows)

### Install (3 minutes)

```bash
# Clone Gator
git clone https://github.com/cumberland-laboratories/gator.git
cd gator

# Gatorize your project
bash gator-engine/scripts/gatorize.sh /path/to/your/project
```

Open your project in your AI tool. The agent reads the entry point, finds the constitution, and starts working within the governance loop. Your first `git commit` will fire the hooks.

→ *Full guide: [Getting Started](getting-started.md)*
→ *Windows-specific: [Installation — Windows](installation.md#windows)*

---

## FAQ

**Does it slow me down?**
No. The governance happens at `git commit`, not during coding. You code at full speed; the hook validates at commit time. A passing commit adds ~200ms.

**Can I override the hook?**
Yes — but only through the Architect approval flow. The agent presents findings to the human supervisor (the Architect), who runs `python .gator/scripts/gator-approve.py` to approve the override with a reason and their name. The override is recorded in commit trailers, so your team can see when and why it was approved. The agent cannot self-approve.

**Does it work with my existing git workflow?**
Yes. Gator adds hooks and files to `.gator/`. It doesn't change your branching strategy, CI/CD, or deployment. It layers on top.

**What if I switch AI tools?**
The governance layer is model-neutral markdown. Switch from Claude to Codex mid-project — the charters, constitution, and session history carry over. Nothing is locked to one vendor.

**What about private/proprietary code?**
Gator's governance operations (hooks, charter validation, trailer assembly, fleet reporting) run entirely locally with no network calls. Your `.gator/` directory is part of your repo, under your access control. The AI coding tools you use with Gator (Claude Code, Codex, etc.) have their own network and privacy characteristics — Gator does not change those.

---

*Cumberland Laboratories — [github.com/cumberland-laboratories](https://github.com/cumberland-laboratories)*
