# Procedure: Architect Override Approval

## When This Applies

The pre-commit hook blocked a commit, and the Architect decides to approve the approvable findings for the exact staged change, instead of fixing them.

## What the Hook Tells You

Every blocked attempt is recorded, and every finding is tagged with how it can be resolved:

| Tag | Meaning | Who resolves it |
|-----|---------|-----------------|
| `[fix-required]` | A correctness problem, such as an invalid `change-type` or a missing message. It can never be approved. | Fix it and retry. |
| `[approvable]` | A charter rule, such as `charter-alongside-code`. | Fix it, or the Architect approves it. |
| `[lint]` | A HIGH or CRITICAL Layer 1 lint finding. | Fix it, or the Architect approves it. |

The hook output ends with a `Block ID` and the command `gator hook override status`.

## What the Agent Does

1. Present the findings to the Architect, with each finding's tag.
2. Fix the `[fix-required]` findings. They block no matter what is approved.
3. For `[approvable]` and `[lint]` findings, the Architect decides: fix them, or approve them.

The agent must NOT run `gator hook approve` (or `gator hook override approve`). The agent must NOT create or edit override files. This is an auditable governance boundary. The agent may run `gator hook override status` and `gator hook override cancel`.

## What the Architect Runs

```
gator hook override status
gator hook approve --reason "<why the override is acceptable>" --name "<Architect name>"
```

`gator hook approve` is the alias of `gator hook override approve`. Both flags are required; if you omit them, the command prompts for them.

**Example:**

```
gator hook approve --reason "Cross-cutting charter already updated in prior commit. No new patterns." --name "Alan Gillette"
```

The command refuses, with the reason, when:

- no blocked attempt is recorded (retry the commit first);
- the staged changes differ from the blocked attempt (retry the commit to record a fresh block);
- the block has expired (after 24 hours);
- nothing in the block is approvable (it names the fix-required findings);
- the block is less than 10 seconds old (the self-approval guard).

After approval, retry `git commit`.

## How the Approval Behaves

- **It is bound to one exact staged change.** If a staged file is added, deleted, renamed, or changed, the approval stops working. Retry the commit to record a new block, and then approve again.
- **It survives a retry that is blocked for another reason.** For example, you approve a charter finding and the retry is then blocked by a fix-required finding. The approval is kept. Fix that finding and retry.
- **It is used up only after the commit lands.** If the commit fails after validation (for example, in `commit-msg`), the approval is still available for the unchanged retry.
- `gator hook override cancel` drops the recorded block and any approval.

## What Gets Recorded

- Commit trailers: `Gator-Override-Approved-By`, `Gator-Override-Block`, `Gator-Override-Reason`, and `Gator-Override-Rules`. When a charter rule was overridden, there is also `Gator-Charter-Changed: override-skip`. The values are sanitized to single lines.
- An `## Overrides` entry in `.gator/whiteboard.md` for that commit.

## Where the State Lives

| File | Location | Tracked? | Lifetime | Agent action |
|------|----------|----------|----------|--------------|
| block / approval / handoff | `.git/gator-override/` (per worktree) | Never (outside the working tree) | From a blocked attempt until the commit lands, `cancel`, or expiry | Inspect with `override status`. Never create or edit. |
| `.gator/commit_issues.md` | working tree | No (gitignored) | Current attempt | Read only. Never stage. |
| `.gator/lint-allow.json` | working tree | Baseline `[]` only | Deprecated: it no longer authorizes lint findings, and the hook never rewrites it | Never add entries. |
| `.gator/.override`, `override-request.json`, `override-approved.json`, `.override-meta.json` | working tree | No (gitignored) | Retired v1 files, removed after the next commit | Never create. `.override` blocks the commit. |

## Connections

-> [Commit Pipeline](../../blueprints/commit-pipeline.md) — the full commit flow, including the override path
-> [Constitution](../constitution.md) — the rules on who can approve overrides
