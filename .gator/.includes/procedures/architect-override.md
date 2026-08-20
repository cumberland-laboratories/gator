# Procedure: Architect Override Approval

## When This Applies

The pre-commit hook blocked a commit and the Architect has decided to approve an override rather than update the affected charters.

## What The Agent Does

When the pre-commit hook blocks with a STOP box, the agent must:

1. Present the findings to the Architect clearly
2. Explain what was blocked and why
3. **Ask the Architect to run the approval command**

The agent must NOT run `gator-approve.py` itself. The agent must NOT create override files. This is an auditable governance boundary.

## What The Architect Runs

The approval script accepts `--reason` and `--name` as CLI flags to avoid interactive prompts:

```
gator hook approve --reason "<why the override is acceptable>" --name "<Architect name>"
```

**Example:**

```
gator hook approve --reason "Cross-cutting charter already updated in prior commit. No new patterns." --name "Alan Gillette"
```

Both flags are required. If omitted, the script falls back to interactive prompts (which may fail in piped or non-interactive contexts).

After approval, the agent retries `git commit` with the same message. The hook validates the approval matches the block ID and consumes it one-shot.

## Flag Reference

| Flag | Required | What it is |
|------|----------|-----------|
| `--reason` | Yes | Why the override is acceptable — recorded in commit trailers |
| `--name` | Yes | The Architect's name — recorded in the approval audit trail |

## What Gets Recorded

The override is not invisible. It produces:

- A `Gator-Override:` trailer in the commit message (visible in git log)
- An entry in `.gator/whiteboard.md` noting the override
- The approval JSON is consumed after the commit (one-shot)

## Connections

-> [Commit Pipeline](../blueprints/commit-pipeline.md) — full commit flow including override path
-> [Constitution](../../constitution.md) — rules governing who can approve overrides
