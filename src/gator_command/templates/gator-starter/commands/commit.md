Commit the current session's work.

Before committing, ensure `commit_draft.md` has structured YAML frontmatter:

```yaml
---
message: "One-line commit message describing the change"
change-type: feature|fix|refactor|docs|test|release|maintenance|review|governance
significance: low|minor|routine|notable|high|critical|architectural
decision-tags: [tag1, tag2]
agent: claude|codex|gemini
architect: AG
---
```

The body of `commit_draft.md` becomes the final commit body. Keep it concise
and reader-facing: explain the outcome, why it matters, and material
verification or compatibility notes. Put detailed implementation inventories,
raw test output, and full significance steelmen in charters or artifacts.

**Steps:**

1. Verify `commit_draft.md` frontmatter is populated (write it if not — you have the context).
2. Stage the tracked code, charter, and documentation files that belong to the commit. Do not force-add the normally ignored `commit_draft.md` runtime file.
3. Run `git commit -F .gator/commit_draft.md`. The pre-commit hook validates charter-alongside-code and a populated draft, writes `.gator/status.json`, and writes warnings to `.gator/whiteboard.md`. The commit-msg hook assembles the final draft message and appends `Gator-*` trailers.
4. If the hook blocks the commit, present the findings to the Architect (they are in the hook output and `.gator/whiteboard.md`). Each finding is tagged:
   - `[fix-required]` — fix it and retry; it can never be approved.
   - `[approvable]` / `[lint]` — fix it, or the Architect may approve this exact staged change.
   `gator hook override status` shows the recorded block at any time (safe for anyone).
5. Let the post-commit hook clear `commit_draft.md` after a successful commit.

`git commit -m` is reserved for the explicit empty-draft compatibility fallback.
With a populated draft, do not invent or maintain a second message.

**Do not run git commit automatically.** The constitution requires Architect confirmation before committing. Present the proposed message and wait for the Architect to approve, adjust, or decline.

**Overrides are Architect-only.** Never approve your own block, and never create override files. The Architect approves in the Gator Dashboard (the repository's **Commits** view, blocked-commit alert), or with `gator hook approve` (alias of `gator hook override approve`) in a terminal; point the Architect to the Dashboard first. Either path authorizes the approvable findings for the exact staged change that was blocked. The approval survives a retry that is blocked for another reason, becomes invalid if the staged change changes, is used up only after the commit lands, and is recorded in the commit trailers. The retired `.gator/.override` file no longer authorizes anything — the hook blocks on it.
