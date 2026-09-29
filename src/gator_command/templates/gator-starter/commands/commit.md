Commit the current session's work.

Before committing, ensure `commit_draft.md` has structured YAML frontmatter:

```yaml
---
message: "One-line commit message describing the change"
change-type: feature|fix|refactor|policy|security|docs
significance: routine|notable|high
decision-tags: [tag1, tag2]
agent: claude|codex|gemini
architect: AG
---
```

The body of `commit_draft.md` remains the free-form session change log.

**Steps:**
1. Verify `commit_draft.md` frontmatter is populated (write it if not — you have the context)
2. Stage all changed files (including `.gator/` files)
3. Read the `message` field from `commit_draft.md` frontmatter
4. Run `git commit -m "<message>"` — the pre-commit hook handles the rest:
   - Validates charter-alongside-code (blocks if code changed but no charter updated)
   - Validates commit_draft is populated
   - Assembles Gator-* trailers and appends them to the commit
   - Writes `.gator/status.json` snapshot
   - Writes any warnings to `.gator/whiteboard.md`
5. If the hook blocks the commit, present the findings to the Architect (they are in the hook output and `.gator/whiteboard.md`). Each finding is tagged:
   - `[fix-required]` — fix it and retry; it can never be approved.
   - `[approvable]` / `[lint]` — fix it, or the Architect may approve this exact staged change.
   `gator hook override status` shows the recorded block at any time (safe for anyone).
6. Clear `commit_draft.md` after successful commit (reset to header only)

**Do not run git commit automatically.** The constitution requires Architect confirmation before committing. Present the proposed message and wait for the Architect to approve, adjust, or decline.

**Overrides are Architect-only.** Never approve your own block, and never create override files. The Architect runs `gator hook approve` (alias of `gator hook override approve`), which authorizes the approvable findings for the exact staged change that was blocked. The approval survives a retry that is blocked for another reason, becomes invalid if the staged change changes, is used up only after the commit lands, and is recorded in the commit trailers. The retired `.gator/.override` file no longer authorizes anything — the hook blocks on it.
