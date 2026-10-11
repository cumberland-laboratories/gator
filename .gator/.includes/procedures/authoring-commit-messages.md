# Procedure: Authoring a Gator Commit Message

`commit_draft.md` is the sole source of truth for a pending Gator commit. The
commit-msg hook turns its `message` field into the summary, copies its body
into the commit body, and appends the `Gator-*` trailers. Do not invent a
separate commit message in `git commit -m`.

## 1. Write the draft for a future reader

Use the frontmatter for structured metadata. Write a short summary that leads
with the outcome. Then write one to five short bullets that explain the user
or maintainer-visible change, why it was made, and any material verification
or compatibility fact.

Good:

```markdown
---
message: "Clarify Gator commit-draft ownership for agents"
change-type: docs
significance: routine
decision-tags: [governance, commit-messages]
agent: codex
architect: Alan Gillette
---

# Session Change Log

- Makes `commit_draft.md` the explicit single source for the final commit message.
- Directs agents to write concise reader-facing summaries instead of implementation logs.
- Documents the hook-owned cleanup and the standard Git invocation.
```

Avoid file-by-file change inventories, raw test output, checkpoint chronologies,
and full significance steelmen. Preserve that detail in a charter, loop record,
or artifact, then link or summarize it only when a reader needs the decision to
understand the commit.

## 2. Stage the change, not the draft runtime state

Stage the code, tracked documentation, and charter updates that belong to the
commit. `commit_draft.md` is normally gitignored hook state. Do not force-add
it: the hook reads the working-tree file when Git commits.

## 3. Commit using the draft as transport

Run:

```text
git commit -F .gator/commit_draft.md
```

`-F` supplies Git an initial non-empty message without creating a second,
competing message. The commit-msg hook replaces that text with the normalized
message assembled from the same draft and adds trailers. Use `git commit -m`
only for the explicit empty-draft compatibility fallback; do not use it for a
populated Gator draft.

After a successful commit, the post-commit hook resets the draft. Do not clear
or re-commit the reset stub yourself.

## Related surfaces

- [Constitution](../constitution.md) — the normative workflow.
- [Committing Gator Files](committing-gator-files.md) — which `.gator/` files
  are tracked work versus local residue.
- [Expected Governance Residue](../reference-notes/expected-governance-residue.md)
  — why a legacy tracked draft may remain modified after a commit.
