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
5. If the hook blocks the commit, read `.gator/whiteboard.md` and present the findings to the Architect
6. Clear `commit_draft.md` after successful commit (reset to header only)

**Do not run git commit automatically.** The constitution requires Architect confirmation before committing. Present the proposed message and wait for the Architect to approve, adjust, or decline.

**Override** (emergency only): write `charter-skip` to `.gator/.override` before committing: `echo charter-skip > .gator/.override && git commit -m "msg"`. The hook reads and deletes the file — one file, one commit, no sticky state. The override is audited in trailers and whiteboard.md — it cannot be hidden.
