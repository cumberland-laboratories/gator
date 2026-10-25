# Procedure: Dangerous-Pattern Warnings

## When This Applies

The pre-commit hook reports a HIGH or CRITICAL dangerous pattern as a `[warning]` and **pauses** the commit (`dangerous-pattern-pause [pause]`, with the box **PAUSE. Architect attention required**) until each finding has a recorded decision. The pause has no approval command: the decision is recorded in `commit_draft.md`.

If the hook instead tags the finding `[external-approval]` (Enterprise `evidence_only`), follow [`architect-override.md`](architect-override.md).

## What the Agent Does

1. **Present each finding to the Architect.** Give the rule, the file and line, the severity, and what the pattern means in this change. The finding is also in `.gator/commit_issues.md` and `.gator/whiteboard.md`.
2. **Stop and ask the Architect to decide.** The choices are:
   - **Fix** the code, or **remove** it. Then no record is needed, and the retry passes.
   - **Keep** it. Then record the Architect's decision (below) and retry.
3. **Never acknowledge a finding yourself.** Record a keep decision only on the Architect's direction, in the Architect's words.

The best time to ask is before you write or run the pattern. See [`reference-notes/dangerous-patterns.md`](../reference-notes/dangerous-patterns.md). Then the decision is in `commit_draft.md` before the first commit attempt, and the commit does not pause.

## Proceeding Without an Architect Decision (Recorded Skip)

Some agents or situations will not stop to ask. Gator does not prevent that, but it records it. The pause prompts human involvement and records every bypass; it does not enforce the Architect's approval. List the keys in the optional field `dangerous-pattern-skips: [RULE@path:line]`. The commit then passes and carries the trailer `Gator-Dangerous-Patterns-Unacknowledged: <keys>`. The Commits view shows it as **! Unacknowledged**. Use a skip only when the Architect cannot be asked; never present a skip as the Architect's decision. A skipped key must be a current warning finding, listed once, and not also acknowledged.

## How to Record a Keep Decision

Each finding has a key: `RULE@path:line`. The path uses forward slashes. A dangerous filename has line `0`. A path character that the draft list cannot hold is percent-encoded: `,` is `%2C`, `[` is `%5B`, `]` is `%5D`, a quotation mark is `%22` or `%27`, a backtick is `%60`, `%` is `%25`, a control character is `%XX`, and a space at either end is `%20`. Other characters, including inner spaces, stay as they are. The hook prints the current keys in its output and in `.gator/status.json` (`commit_checks.dangerous_pattern_warnings`). Copy each key exactly as printed.

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

A warning without any recorded decision pauses the commit (`dangerous-pattern-pause`). The pause lists the keys that still need a decision.

## What Gets Recorded

- The commit body keeps the `## Architect acknowledgement` section.
- Two trailers: `Gator-Dangerous-Patterns: <keys>` and `Gator-Dangerous-Pattern-Acknowledged-By: <architect>`. They never contain the matched source text.
- `.gator/status.json` `commit_checks.dangerous_pattern_acknowledged` and `acknowledged_by`, and an `## Architect acknowledgements` whiteboard section.
- For a recorded skip: the `Gator-Dangerous-Patterns-Unacknowledged` trailer, `commit_checks.dangerous_pattern_skipped`, and an `## Unacknowledged dangerous patterns (recorded skip)` whiteboard section.

An acknowledgement is not an override. It does not create, use, or cancel an approval, and it never produces `Gator-Override-*` trailers.

## Limits

- The pause and its record depend on the agent's honesty: an agent could write a skip, or even an acknowledgement, without asking. A skip is always visible as unacknowledged; a forged acknowledgement is not distinguishable in Git.
- If the commit-msg phase cannot revalidate the recorded evidence (for example, a read error), the commit fails rather than landing without its trailers. Retry the commit.

## Connections

-> [Architect Override Approval](architect-override.md) — the external-approval path
-> [Authoring a Gator Commit Message](authoring-commit-messages.md) — the draft fields
-> [Dangerous Patterns](../reference-notes/dangerous-patterns.md) — surfacing patterns during the session
