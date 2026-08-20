# Charter Alignment Procedure

**When to use**: Periodically during a session, and immediately when the code appears to deviate from what a charter describes.

## Why This Exists

Charters are only useful if they reflect reality. The constitution requires updating charters with every code change, but drift still happens -- changes made outside a Gator session, changes where the charter update was incomplete, or charters that were never fully accurate to begin with.

This procedure gives the primary agent a way to detect and resolve drift before it causes problems.

## When to Check Alignment

### Periodic checks (proactive)

The agent should periodically verify alignment during a session:

- **At session open**: After reading the relevant charters, do a quick sanity check -- do the function names in the charter still exist in the code? Does the "Owns" section still match what the module actually does?
- **Before a significant change**: If about to modify a module, check that the charter's description of that module matches the current code state. If it doesn't, resolve the discrepancy first.
- **Before commit**: As part of the pre-commit checklist, confirm that charter updates in this session's commits correspond to the code changes in those same commits.

### Reactive checks (when something seems off)

If the agent notices any of these, **stop and check alignment before proceeding**:

- A function name referenced in a charter doesn't exist in the code
- A charter says a module "Does Not Own" something, but the code contains that logic
- A TRIPWIRE pattern described in the cross-cutting charter no longer matches the code
- The callers (`<-`) or callees (`->`) listed in a charter don't match what grep shows
- The code does something the charter doesn't mention at all
- The agent's plan conflicts with what the charter describes

## How to Check

### Quick check (30 seconds)

```
1. Read the relevant charter
2. Grep for the function names it lists -- do they still exist?
3. Scan the "Owns" and "Does Not Own" -- does the code still respect these boundaries?
4. Check any TRIPWIREs -- are the described patterns still present?
```

### Git history check (when drift source is unclear)

```
1. git log --oneline -- <module-path>          # recent code changes
2. git log --oneline -- .gator/charters/<charter>.md   # recent charter changes
3. Compare: do code changes have corresponding charter updates?
4. If not, identify which commits changed code without updating the charter
```

If code was changed without charter updates, the charter is stale. If the charter was updated but the code doesn't match, the code may have regressed or the charter update was wrong.

### Full alignment audit (when drift is significant)

For deeper misalignment, ask the Architect to run the enforcer review script or a CLI enforcer focused on charter accuracy:

```bash
# Enforcer review script (uses configured model, diff-based)
gator hook enforcer-review

# CLI enforcer (separate model, full repo-wide audit, no diff needed)
codex review "Read all charters in .gator/charters/. Read the code they cover. Report any places where the code has drifted from what the charters describe -- missing functions, stale entries, boundary violations, and broken cross-references."
```

## How to Resolve

When a discrepancy is found:

1. **Present the discrepancy to the Architect**: "The charter says X, but the code does Y. Which is correct?"
2. **Don't assume the code is right**: Sometimes the charter is the intent and the code has drifted. The Architect decides.
3. **Fix whichever is out of date**:
   - If the charter is stale: update the charter to match the code
   - If the code is wrong: fix the code to match the charter (the charter represents the intended design)
   - If both need updating: work with the Architect to establish what the intent should be, then update both
4. **Log the alignment fix**: Add a bullet to `commit_draft.md` noting the drift and how it was resolved

## What the Agent Should NOT Do

- Don't silently "fix" a charter to match code that might be wrong
- Don't ignore a discrepancy and proceed with the change anyway
- Don't treat alignment as a one-time bootstrap activity -- it's ongoing
- Don't assume recent code is more correct than the charter -- the Architect decides
