# Procedure: Dangerous-Pattern Warnings

## When This Applies

The pre-commit hook reports a HIGH or CRITICAL dangerous pattern as a `[warning]`, with the line **Architect attention required**. Under the default policy the warning does not block the commit and has no approval command.

If the hook instead tags the finding `[external-approval]` (Enterprise `evidence_only`), follow [`architect-override.md`](architect-override.md).

## What the Agent Does

1. **Present each finding to the Architect.** Give the rule, the file and line, the severity, and what the pattern means in this change. The finding is also in `.gator/commit_issues.md` and `.gator/whiteboard.md`.
2. **Ask the Architect to decide.** The choices are:
   - **Fix** the code, or **remove** it. Then no acknowledgement is needed.
   - **Keep** it. Then record the Architect's decision (below).
3. **Never acknowledge a finding yourself.** Record a keep decision only on the Architect's direction, in the Architect's words.

The best time to ask is before you write or run the pattern. See [`reference-notes/dangerous-patterns.md`](../reference-notes/dangerous-patterns.md). A commit whose only finding is a warning lands at once. So a keep decision is recorded in Git only if it is in `commit_draft.md` before the commit that contains the finding. If the commit has already landed, tell the Architect. The decision stays in the conversation, or the Architect asks for a follow-up commit to fix the finding.

## How to Record a Keep Decision

Each finding has a key: `RULE@path:line`. The path uses forward slashes. A dangerous filename has line `0`. The hook prints the current keys in its output and in `.gator/status.json` (`commit_checks.dangerous_pattern_warnings`).

In `commit_draft.md`, add the keys to the frontmatter and explain each one in a body section:

```markdown
---
message: "Add the encrypted test fixture"
change-type: test
significance: notable
decision-tags: [security, decision]
agent: <agent>
architect: <Architect name>
dangerous-pattern-acknowledgements: [HYG-002@.env:0]
---

# Session Change Log

- Adds the encrypted fixture the integration tests need.

## Architect acknowledgement

- `HYG-002@.env:0`: Keep this encrypted test fixture. The Architect confirmed it belongs in the repository for this change.
```

Rules:

- The `architect` field must name the Architect. The legacy `pi` field is not accepted for this evidence.
- List each key once. Give each listed key exactly one bullet, `- \`KEY\`: <decision>`, with text after the colon.
- List only current HIGH or CRITICAL warning findings. Do not list MEDIUM or LOW findings, or `[external-approval]` findings.
- Do not put the matched source text in the draft.

## What the Hook Checks

When the evidence is present, the hook checks it against the staged change. Any problem blocks the commit as `invalid-dangerous-pattern-acknowledgement` `[fix-required]`, and the message names the current keys:

- a key that names no current warning: stale, a wrong line, invented, or not a HIGH or CRITICAL warning;
- a duplicate key, or a key that is not in `RULE@path:line` form;
- an empty `architect` field;
- a missing `## Architect acknowledgement` section, a missing or empty bullet, or a bullet for a key that is not listed;
- a section without any listed keys.

If a line moves and a key goes stale, confirm the decision with the Architect again and update the key. If you fixed or removed the finding, remove its key; a fixed finding needs no acknowledgement.

A warning without any evidence never blocks.

## What Gets Recorded

- The commit body keeps the `## Architect acknowledgement` section.
- Two trailers: `Gator-Dangerous-Patterns: <keys>` and `Gator-Dangerous-Pattern-Acknowledged-By: <architect>`. They never contain the matched source text.
- `.gator/status.json` `commit_checks.dangerous_pattern_acknowledged` and `acknowledged_by`, and an `## Architect acknowledgements` whiteboard section.

An acknowledgement is not an override. It does not create, use, or cancel an approval, and it never produces `Gator-Override-*` trailers.

## Limits

- A key cannot be written in the flat frontmatter list when its path contains `,`, `[`, `]`, or a quotation mark. Such a finding stays an unacknowledged warning.

## Connections

-> [Architect Override Approval](architect-override.md) — the external-approval path
-> [Authoring a Gator Commit Message](authoring-commit-messages.md) — the draft fields
-> [Dangerous Patterns](../reference-notes/dangerous-patterns.md) — surfacing patterns during the session
