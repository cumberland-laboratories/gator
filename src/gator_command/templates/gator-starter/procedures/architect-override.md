# Procedure: Architect Override Approval

## When This Applies

The pre-commit hook blocked a commit with an `[external-approval]` finding, and the Architect decides to approve it for the exact staged change, instead of fixing it.

Two findings are `[external-approval]`:

- **A missing charter update** (`charter-alongside-code`, `charter-index-gap`), in every repository. Normally the agent updates the charter. The Architect approves instead only when no charter edit is warranted: the check misfired (for example, the INDEX routes a file to the wrong charter), or the change is too small to describe.
- **A HIGH or CRITICAL dangerous pattern**, only in an Enterprise `evidence_only` repository.

Under the default policy, a dangerous pattern is a `[warning]` that pauses the commit until the Architect's decision is recorded in `commit_draft.md`. The pause has no approval command (see [`dangerous-pattern-warnings.md`](dangerous-pattern-warnings.md)).

## What the Hook Tells You

Every blocked attempt is recorded, and every finding is tagged with how it is resolved:

| Tag | Meaning | Who resolves it |
|-----|---------|-----------------|
| `[fix-required]` | A correctness problem, such as an invalid `change-type`, a missing message, or invalid acknowledgement evidence. It can never be approved. | Fix it and retry. |
| `[external-approval]` | A missing charter update, or a HIGH or CRITICAL dangerous pattern in a mode that requires external approval. | Fix it (update the charter), or the Architect approves it. |
| `[warning]` / `[pause]` | A HIGH or CRITICAL dangerous pattern under the default policy, and the `dangerous-pattern-pause` it causes. No approval command: record the Architect's decision (or an explicit skip) in `commit_draft.md`. | The Architect, in the session. |

The hook output ends with a `Block ID` and the command `gator hook override status`. The STOP box that names the approval (the Dashboard's Commits view, or `gator hook approve` in a terminal) appears only when an `[external-approval]` finding is present.

## What the Agent Does

1. Present the findings to the Architect, with each finding's tag.
2. Fix the `[fix-required]` findings. They block no matter what is approved.
3. For `[external-approval]` findings, the Architect decides: fix them, or approve them. For a missing charter update, the default is to update the charter; suggest approval only when you can say why no charter edit is warranted.
4. When the Architect chooses approval, point them to the **Gator Dashboard first**: the repository's **Commits** view shows a blocked-commit alert (⚑) that opens the approval dialog. Mention `gator hook approve` only as the terminal alternative. Do not send the Architect to the command line by default.

The agent must NOT approve: not in the Dashboard, and not with `gator hook approve` (or `gator hook override approve`). The agent must NOT create or edit override files. This is an auditable governance boundary. The agent may run `gator hook override status` and `gator hook override cancel`.

## How the Architect Approves

**In the Gator Dashboard (the default).** Open the repository's **Commits** view. While a commit is blocked it shows an alert (for example "⚑ Commit blocked"). The alert opens a dialog that groups the findings as External approval, Architect decision required and Fix required. Enter your name and a reason, and choose **Approve**. Approve is offered only for findings that still need an approval, after the ten-second guard. The dialog runs the same repository command as the terminal and writes the same approval and trailers.

**In a terminal (the alternative).**

```
gator hook override status
gator hook approve --reason "<why the override is acceptable>" --name "<Architect name>"
```

`gator hook approve` is the alias of `gator hook override approve`. Both flags are required; if you omit them, the command prompts for them.

**Example:**

```
gator hook approve --reason "Typo fix in a log message; no charter content changes." --name "Alan Gillette"
```

Both paths refuse, with the reason, when:

- no blocked attempt is recorded (retry the commit first);
- the staged changes differ from the blocked attempt (retry the commit to record a fresh block);
- the block has expired (after 24 hours);
- nothing in the block is approvable (it names the fix-required findings);
- the block was recorded by an earlier Gator runtime (cancel and retry; see Migration);
- the block is less than 10 seconds old (the self-approval guard).

After approval, retry `git commit`.

## How the Approval Behaves

- **It is bound to one exact staged change.** If a staged file is added, deleted, renamed, or changed, the approval stops working. Retry the commit to record a new block, and then approve again.
- **It survives a retry that is blocked for another reason.** For example, you approve a charter finding and the retry is then blocked by a fix-required finding. The approval is kept. Fix that finding and retry.
- **It is used up only after the commit lands.** If the commit fails after validation (for example, in `commit-msg`), the approval is still available for the unchanged retry.
- **It never clears a `[fix-required]`, `[warning]` or `[pause]` finding.** A commit with a charter finding and a paused dangerous pattern needs both: the approval for the charter, and the recorded decision for the pattern.
- `gator hook override cancel` drops the recorded block and any approval.

## Migration From Earlier Runtimes

Before this policy, charter rules were tagged `[approvable]` and every HIGH or CRITICAL lint finding was `[lint]`. Gator does not reinterpret those records.

- If a commit blocks on `legacy-override-record`, an earlier runtime left a block or approval for the same staged change. Run `gator hook override cancel` and retry. The block repeats on every unchanged retry until you cancel.
- An earlier approval is never carried over. After the retry, a missing charter update blocks as `[external-approval]` (approve it again if it is still warranted), and a dangerous pattern pauses for a recorded decision under the default policy.
- A record for a different staged change, or an expired one, does not block. The next successful commit retires it.
- An Enterprise `evidence_only` block finishes under the same envelope: its findings are now tagged `[external-approval]`.

## What Gets Recorded

- Commit trailers: `Gator-Override-Approved-By`, `Gator-Override-Block`, `Gator-Override-Reason`, and `Gator-Override-Rules`. The values are sanitized to single lines. When a charter rule was approved, there is also `Gator-Charter-Changed: override-skip`.
- An `## Overrides` entry in `.gator/whiteboard.md` for that commit, and `overridden_rules` in `.gator/status.json` `commit_checks`.

## Where the State Lives

| File | Location | Tracked? | Lifetime | Agent action |
|------|----------|----------|----------|--------------|
| block / approval / handoff | `.git/gator-override/` (per worktree) | Never (outside the working tree) | From a blocked attempt until the commit lands, `cancel`, or expiry | Inspect with `override status`. Never create or edit. |
| `.gator/commit_issues.md` | working tree | No (gitignored) | Current attempt | Read only. Never stage. |
| `.gator/lint-allow.json` | working tree | Baseline `[]` only | Deprecated: it no longer changes how lint findings are handled, and the hook never rewrites it | Never add entries. |
| `.gator/.override`, `override-request.json`, `override-approved.json`, `.override-meta.json` | working tree | No (gitignored) | Retired v1 files, removed after the next commit | Never create. `.override` blocks the commit. |

## Connections

-> [Gator Architecture Overview](../../blueprints/gator-architecture-overview.html#commit) — the commit gate, including the block and approval path (Gator source repository)
-> [Constitution](../constitution.md) — the rules on who can approve overrides
