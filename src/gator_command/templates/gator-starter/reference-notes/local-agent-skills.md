# Local Agent Skills — Personal Notes Alongside Gator Governance

## The Pattern

Gator's governance lives in `.gator/`. A session starts with `gator init`, which names `GATOR_INIT.md` and then the constitution and context files. Vendor instruction files at the repo root — `CLAUDE.md`, `AGENTS.md` (for Codex), `GEMINI.md` — are optional and belong to your repository. Gator never creates, edits, or refreshes them. What a team writes there is the repo's shared instructions to the agent.

But sometimes you want personal notes, skills, or workflows that are just for **you on this machine** — not for teammates and not for review. That's what the `*.local.md` companion pattern is for. Create `CLAUDE.local.md` (or `AGENTS.local.md` / `GEMINI.local.md`) at the repo root. `gatorize` and `gator update` add these filenames to your `.gitignore` automatically, so they stay on your machine and never enter Git. Gator never reads or writes them.

## What Belongs Where

Three surfaces exist. Pick the one that matches how the content should travel:

- **Gator governance in `.gator/`**: `GATOR_INIT.md`, the constitution, charters, procedures. Shipped parts refresh on `gator update`; your charters and procedures travel through PRs.
- **Your vendor files** (`CLAUDE.md` / `AGENTS.md` / `GEMINI.md`, tracked in Git): repo-shared, tool-specific instructions to the agent. Team-visible, reviewable, part of every clone. A one-line pointer to `gator init` is enough to make the tool start Gator on its own.
- **The `*.local.md` companion** (gitignored, machine-local): personal notes, private skills, one-off workflows, personal debugging aides. Yours alone.

Precedence, when the agent reads all three:

1. **Gator governance** — `GATOR_INIT.md`, the constitution, charters. Non-negotiable.
2. **Repo-shared tracked content** — team policy in your vendor files and `.gator/procedures/`. Reviewable by the team. May extend Gator governance; must not override it.
3. **Local companion** — personal guidance. May extend behavior; **must not override** the layers above.

Repositories gatorized by an older Gator version may still have a `<!-- GATOR:BEGIN -->` … `<!-- GATOR:END -->` block in a vendor file. Gator no longer refreshes it; where it disagrees with `GATOR_INIT.md` or the constitution, those win. Keep it, trim it to a pointer, or remove it.

## Format Example

A minimal `CLAUDE.local.md` (`AGENTS.local.md` and `GEMINI.local.md` follow the same shape):

```markdown
# Personal Notes

## Skills

- **Prefer terse commit messages.** One-line summary, no trailing body unless the change is complex.
- **Run pytest with `-x`** locally so the first failure stops the run.
- **When editing `dashboard/`,** launch the dev server on port 8899 (not the default 8080) — 8080 is my other repo.

## Scratch

Anything personal — TODO reminders, notes about local branches, workflow shortcuts.
```

Keep it short. Grow it as you notice friction. Nothing here is shared with teammates or ships anywhere.

## Team-vs-Personal — The Decision Guide

If more than one person on the team would benefit, it is not personal. Route it to a tracked surface:

| Signal | Route it to |
|---|---|
| "Everyone on the team should read this before touching auth code" | `.gator/charters/` (module invariants) |
| "This is our standard PR-review checklist" | `.gator/procedures/` (team workflows) |
| "This is how *I* like to structure my local test runs" | `CLAUDE.local.md` (personal) |
| "This one-off script helps me debug prod on my laptop" | `CLAUDE.local.md` (personal) |
| "The team's install-from-scratch recipe" | `.gator/procedures/` (team) |

When in doubt, ask: would a teammate cloning this repo tomorrow benefit from seeing this? If yes, it's team-shared. If no, it's personal.

## How to Add a Team-Shared Skill

Personal skills travel by staying local. Team-shared skills travel through your team's normal Git workflow:

1. Author a new charter in `.gator/charters/` or a new procedure in `.gator/procedures/`.
2. Commit it on a feature branch.
3. Open a PR — teammates review it as team policy.
4. Merge. Teammates pick up the new content on their next `git pull`.

**Note on cross-repo distribution.** Gator today does not itself distribute repo-authored charter or procedure content *between* repos. Team-shared content travels with your team's Git workflow — one repo at a time, through PRs. A native cross-repo distribution surface for team-authored skills is a future direction (tracked in the Local Agent Overrides + Managed State plan, Stage 6).

## Why It Matters

The alternative is that every developer adds personal notes to the tracked vendor file itself. That creates merge conflicts on every branch that touches it, and it leaks one person's workflow to everyone else who clones the repo. The `*.local.md` companion pattern gives you a private surface without polluting the shared one.

## See Also

- `GATOR_INIT.md` (named by `gator init`) — Gator's entry document and the start of every governed session.
- `.gator/charters/` — team-shared knowledge about module invariants.
- `.gator/procedures/` — team-shared workflows and recipes.
