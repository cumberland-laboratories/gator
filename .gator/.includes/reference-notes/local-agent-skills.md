# Local Agent Skills — Personal Notes Alongside a Governed Entry Point

## The Pattern

Every Gator-governed repo has one or more agent entry-point files at the root — `CLAUDE.md`, `AGENTS.md` (for Codex), `GEMINI.md`. Gator manages a block inside each of these files (the `<!-- GATOR:BEGIN -->` … `<!-- GATOR:END -->` region) and refreshes it on `gator update`. Anything outside that block is your repo's shared instructions to the agent.

But sometimes you want personal notes, skills, or workflows that are just for **you on this machine** — not for teammates and not for review. That's what the `*.local.md` companion pattern is for. Create `CLAUDE.local.md` (or `AGENTS.local.md` / `GEMINI.local.md`) next to the tracked entry-point file. `gatorize` and `gator update` add these filenames to your `.gitignore` automatically, so they stay on your machine and never enter Git.

## What Belongs Where

Three surfaces exist. Pick the one that matches how the content should travel:

- **The Gator-managed block** (inside `<!-- GATOR:BEGIN/END -->`): governance instructions Gator ships and refreshes. You do not edit this.
- **The rest of the entry-point file** (outside the managed block, but tracked in Git): repo-shared instructions to the agent. Team-visible, reviewable, part of every clone.
- **The `*.local.md` companion** (gitignored, machine-local): personal notes, private skills, one-off workflows, personal debugging aides. Yours alone.

Precedence, when the agent reads all three:

1. **Managed block** — Gator governance. Non-negotiable.
2. **Repo-shared tracked content** — team policy in the entry-point file, `.gator/procedures/`, `.gator/charters/`. Reviewable by the team.
3. **Local companion** — personal guidance. May extend behavior; **must not override** the layers above.

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

The alternative is that every developer adds personal notes to the tracked entry-point file itself. That creates merge conflicts on every branch that touches it, and it leaks one person's workflow to everyone else who clones the repo. The `*.local.md` companion pattern gives you a private surface without polluting the shared one.

## See Also

- The `<!-- GATOR:BEGIN/END -->` block in your entry-point file — canonical instructions that reference this note.
- `.gator/charters/` — team-shared knowledge about module invariants.
- `.gator/procedures/` — team-shared workflows and recipes.
