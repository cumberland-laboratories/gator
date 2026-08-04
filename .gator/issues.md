# Issues (retired)

> **This file is no longer the tracker.**
>
> Bugs, features, refactors, packaging chores, and other durable work items live in **[GitHub Issues](https://github.com/cumberland-laboratories/gator/issues)**, organized on the [Gator project board](https://github.com/users/cumberland-laboratories/projects/1). This move landed 2026-08-04 — see the design outline at `.gator/vault/artifacts/2026-08-04-github-issue-tracking-outline.md` and the migration procedure at `.gator/procedures/file-github-issue.md`.
>
> **Where things go now**:
> - New bugs/features/tasks → [file a GitHub Issue](https://github.com/cumberland-laboratories/gator/issues/new) (follow `.gator/procedures/file-github-issue.md`)
> - Half-formed ideas / triage buffer → `.gator/inbox.md`
> - Architectural memory, invariants, cross-module contracts → `.gator/charters/`
> - Implementation plans, artifacts, design records → `.gator/artifacts/` (or `.gator/vault/artifacts/` when private)
>
> This file stays in the tree (rather than being deleted) so that `gator-pulse.py`, `gator_layout.py::get_gator_paths()`, and other readers that expect `.gator/issues.md` to exist continue to resolve it cleanly. It's a deliberate stub, not an oversight.

## Historical entries

The full history of `.gator/issues.md` (six numbered entries #1-#6, ranging from cosmetic trailer bugs to migration convergence failures, mix of resolved and open) is preserved in git. To read it:

```
git log --follow --all -p -- .gator/issues.md
```

Or browse the last-populated version on GitHub before the retirement commit landed.

At the moment of retirement:

- **Resolved** items #2 (Dashboard `gator-command/` sidebar — false alarm) and #6 (migrate_layout Step 5 dir conflicts, shipped in v2.5.4 commit `5453f8b`) had their fixes committed and their resolution notes preserved in the git-history version.
- **Open** items #1 (Gator-Charter-Changed trailer miss), #3 (Dashboard swallows update errors), #4 (release-candidate.yml RC-suffix injection), and #5 (Node.js 20 deprecation) were migrated to GitHub Issues #2, #1, #3, and #4 respectively on 2026-08-04 with full context bodies + Priority + Area metadata on the Gator project board.
