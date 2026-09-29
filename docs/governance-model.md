# Governance Model

Gator's governance is structural, not purely behavioral. It enforces rules at commit time with deterministic hooks that run as a separate process outside the agent's prompt loop.

## Three Layers

### 1. Constitution

The constitution is a machine-readable document that tells AI agents what they can and cannot do in a repo. Every session starts by reading it.

Constitutions define:

- What the repo is (scope, boundaries)
- How agents should work (read charters before coding, update charters alongside code)
- What's off-limits (never modify certain files, never skip hooks)

The per-repo constitution (`.gator/constitution.md`) inherits from the command post's organizational policy. Changes at the org level propagate to all repos at next session start.

### 2. Charters

Charters are structured maps of code modules — what each function does, who calls it, what models it touches, and where the non-obvious behavior lives.

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

Key notations:

- `←` / `→` — dependency traces (who calls this, what this calls)
- `R` / `W` / `RW` — access patterns (predict side effects without reading the function)
- `!` — tripwires (non-obvious behavior that breaks if you miss it)

Charters are created and maintained by the AI agent, not the human. The agent reads the code, writes the charter, and updates it whenever the code changes. The pre-commit hook enforces that charter updates accompany code changes — if the agent changed code but didn't update the charter, the commit is blocked. The human reviews charters for accuracy but does not author them.

### 3. Pre-Commit Hook

A deterministic pre-commit hook fires on every `git commit`:

- **Charter-alongside-code** — code changed but no charter updated? Blocked.
- **Trailer assembly** — reads the session's commit draft, assembles `Gator-*` trailers (change type, significance, charter status, agent identity)
- **Whiteboard findings** — suspicious patterns get written to `.gator/whiteboard.md`

The hook is a separate process — its decision is deterministic and cannot be influenced by the agent's reasoning. A blocked commit produces a STOP box designed as an attention spike that is designed to cause the agent to pause and present findings to the Architect. Note: the current gate is behavioral, not cryptographic. A determined model could technically self-approve or skip hooks. Token-based approval requiring an Architect-held secret is under consideration for future versions.

## The Review Wall

The enforcer (code reviewer) is always a different model than the coding agent. Same-model review is not enforcement.

- Coding agent writes code, updates charters, prepares commit
- Pre-commit hook validates (deterministic, no LLM)
- Enforcer model reviews findings from a different trust boundary

Different training means different blind spots. The wall between coding and reviewing is the feature.

→ *Full guide: [Enforcer Patterns](enforcer-patterns.md) — deployment options, model pairing, and the high-supervision philosophy*

## Override Protocol

When the hook blocks a commit, it records the blocked attempt with a block ID. Each finding is tagged `fix-required` (it must be fixed), `approvable` (a charter rule), or `lint` (a HIGH/CRITICAL lint finding). The Architect — not the agent — approves:

```bash
gator hook override status
gator hook approve --reason "..." --name "..."
```

(On pre-2.9 repos that still carry repo-resident scripts: `python .gator/scripts/gator-approve.py approve ...`.)

The approval flow:

1. **Hook blocks.** It records the attempt, bound to the exact staged change, with every finding tagged. The record lives in `.git/gator-override/`, never in the working tree.
2. **Architect reviews.** They read the findings and decide whether to approve the approvable ones.
3. **Architect runs `gator hook approve`.** It requires a reason and a name, and writes an approval for that exact staged change only. Fix-required findings can never be approved.
4. **Hook validates on retry.** The approval applies only if the staged change is unchanged. It is kept if the retry is blocked for another reason, and is used up only after the commit lands.
5. **Override recorded.** The `Gator-Override-Approved-By`, `-Block`, `-Reason`, and `-Rules` commit trailers are visible to fleet reports and audits.

The agent may NOT run `gator hook approve` or create override files. Unauthorized self-approval is an auditable governance violation.

Every override across the organization is surfaced by fleet reports and audit dashboards. There is no silent bypass path.

**Note:** The current gate is behavioral, not cryptographic. A determined model could technically circumvent the approval flow. Token-based approval requiring an Architect-held secret is under consideration. See → [Threat Model](threat-model.md) for explicit scope of protection.

> *Retired: the older `echo charter-skip > .gator/.override` mechanism no longer authorizes anything — the hook now blocks when that file exists. The deprecated `.gator/lint-allow.json` likewise no longer suppresses lint findings on its own.*

## Policy Inheritance

```
Command Post (org-policy.md)
    └── propagates via thin link to →
        Fleet Repo (.gator/constitution.md)
            └── enforced by →
                Pre-commit hook (deterministic)
```

A policy change in the command post reaches every governed repo at the next `gator update` or session start. No per-repo edits needed.

## What Gator Protects Against

See → [Threat Model](threat-model.md) for explicit scope: four threat profiles (cooperative agent, sloppy agent, adversarial agent, enterprise), five defense layers, and honest limitations.
