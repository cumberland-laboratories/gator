# Git Workflow

Suggested git process for projects using Gator. Not enforced — adapt to your team and comfort level.

## Two Modes

### Team / Careful Mode

For teams, shared repos, or when changes carry risk.

```
main (stable, deployable)
  └── dev (integration branch)
        ├── feature/add-auth
        ├── feature/refactor-store
        └── fix/query-timeout
```

1. **Branch from dev** for each piece of work (`feature/`, `fix/`, `chore/`)
2. **Work on the branch** — normal Gator loop (read charters, change code, update charters)
3. **PR into dev** — review the diff, check that charters were updated, run enforcer if warranted
4. **Test on dev** — integration, smoke tests, whatever the project needs
5. **Merge dev to main** — when dev is stable and reviewed. This is the release gate.

### Solo / Streamlined Mode

For solo projects or when you're the only one touching the code.

```
main (stable)
  └── dev (working branch)
```

1. **Work on dev** — normal Gator loop
2. **When happy, commit to dev**
3. **Merge dev to main** — when the work is complete and you're confident

No feature branches needed. Dev is your working surface, main is your "known good" state.

## Which Mode?

| Situation | Use |
|-----------|-----|
| Solo project, one contributor | Streamlined |
| Team, shared repo | Team mode |
| Solo but high-stakes (production, public API) | Team mode — the branch discipline protects you |
| Early prototyping, exploring | Streamlined — don't let process slow discovery |

## How Gator Fits

- **Charters update on the working branch**, not on main. They travel with the code.
- **Enforcer reviews happen before PR or before merge** — the Architect decides when and at what level.
- **commit_draft.md accumulates on the working branch until commit time** — use it to draft the next commit message or PR context, then clear it immediately after the commit so the next session starts fresh.
- **Don't branch .gator/ separately from code.** The knowledge layer and the code must stay in sync. If you branch the code, the charters go with it.

## What to Avoid

- Don't commit directly to main during active development. Even in solo mode, use dev as a buffer.
- Don't let feature branches live longer than a few days. Long-lived branches mean charter drift.
- Don't merge without checking that charters reflect the current code state. The enforcer can catch this, but it's faster to just look.
