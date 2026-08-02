# Custom Skills and Team Workflow

A practical guide to what Gator manages, what stays yours, and how teams share AI-coding skills through a Gator-governed repo. Written for prospective adopters and for teammates joining a repo that already has Gator installed.

If you have not installed Gator yet, start with [How to Use Gator](how-to-use-gator.md).

## What Are "Skills" in Agent-Tool Land?

Modern AI coding assistants (Claude Code, Codex CLI, Gemini CLI) all take three kinds of guidance:

- **Slash commands** — short authored prompts you invoke by name in a session (e.g. `/init`, `/review`). Vendors store them under `.claude/commands/`, `.codex/commands/`, or `.gemini/commands/` in the repo.
- **Entry-point instructions** — free-form markdown the tool reads on session start. Vendors call this `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` at the repo root. It sets tone, priorities, and standing rules for the agent.
- **Personal notes** — the same shape as entry-point instructions, but scoped to one person on one machine.

All three are just markdown or short prompt files. Nothing about them is Gator-specific. What Gator adds is a discipline around who owns which surface, so the team's shared setup doesn't get overwritten by an update and your personal setup doesn't leak into the team's Git history.

## What Happens to Your `.claude/` (or `.codex/`, `.gemini/`) on Install

When you run `gator gatorize` on a repo, four Gator-owned slash commands land in the vendor `commands/` directory:

- `init.md` — orients the agent to the constitution, mission, and roadmap at session start.
- `update.md` — runs a template refresh.
- `commit.md` — walks the pre-commit governance loop.
- `loop-join.md` — joins a Gator Loop (multi-agent governed planning).

Two rules apply to these files:

1. **Existing non-Gator commands are backed up with a `.pre-gator` suffix before overwrite.** If you already had a `.claude/commands/init.md` that did something different, gatorize renames it to `init.pre-gator.md` so nothing is silently lost.
2. **Existing Gator commands are refreshed silently.** `gator update` overwrites Gator-owned commands with the current template versions; that is intentional so improvements to the shared prompts reach every repo.

**User-authored slash commands you add later are preserved.** If you author `.claude/commands/review.md` yourself, `gator update` leaves it alone.

Vendor `SessionStart` hook configs (`.claude/settings.json`, `.codex/hooks.json`, `.gemini/settings.json`) get merged non-destructively: Gator's hook entries are inserted alongside any hooks you already had. Your permissions, environment variables, and non-Gator hooks are never touched.

## What Happens to Your Custom Instructions in `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`

The three entry-point files at the repo root use a **managed block** pattern:

```markdown
# Claude Code Entry Point

You are the primary agent for this project.

<!-- GATOR:BEGIN -->
... Gator-owned governance instructions live here ...
<!-- GATOR:END -->

## Team Notes

Anything you write outside the sentinels is your repo's shared instructions.
```

Inside the sentinels is Gator territory. `gator update` refreshes that block in place.

**Outside the sentinels is your territory.** Anything you write above or below the block — team-shared instructions, project conventions, custom personas — is preserved across every update.

> **📷 Screenshot (TODO — `docs/images/managed-block-in-editor.png`):** A real `CLAUDE.md` opened in an editor with the `<!-- GATOR:BEGIN -->` and `<!-- GATOR:END -->` sentinels visible, some team-authored content above the block and the Gator-managed content inside it. This is the entire doc's central concept made visible — one screenshot beats three paragraphs.

Before Gator overwrites the managed block, it writes a `.pre-gator-update` sibling backup of the file (`CLAUDE.md.pre-gator-update`) whenever the update makes real changes. If you had unintended edits inside the block, the backup is right there. Review it and roll back the parts you want with a normal git edit.

> **📷 Screenshot (TODO — `docs/images/pre-gator-update-backup.png`):** File browser (VS Code sidebar or similar) showing `CLAUDE.md` and its sibling `CLAUDE.md.pre-gator-update` right below it, both freshly modified. The safety net made tangible — "your unintended edits are one file away."

## Personal Skills, Per-Machine — the `*.local.md` Companion

Sometimes you want personal notes that are just for **you on this machine** — not for the team and not for review.

Create a companion file next to the tracked entry point:

- `CLAUDE.local.md` (paired with `CLAUDE.md`)
- `AGENTS.local.md` (paired with `AGENTS.md`)
- `GEMINI.local.md` (paired with `GEMINI.md`)

`gatorize` and `gator update` add these filenames to your `.gitignore` automatically, so they never enter Git. Gator itself never reads, writes, or refreshes them.

> **📷 Screenshot (TODO — `docs/images/tracked-vs-local-file-browser.png`):** File browser view showing `CLAUDE.md` (normal color, tracked) next to `CLAUDE.local.md` (greyed/italicized, gitignored) — VS Code or similar renders these distinctly. The visual distinction is the whole point: team content in Git, personal content on your machine.

A minimal `CLAUDE.local.md`:

```markdown
# Personal Notes

## Skills

- **Prefer terse commit messages.** One-line summary, no trailing body unless the change is complex.
- **Run pytest with `-x`** locally so the first failure stops the run.
- **When editing `dashboard/`,** launch the dev server on port 8899 — 8080 is my other repo.

## Scratch

Anything personal — TODO reminders, notes about local branches, workflow shortcuts.
```

Keep it short. Grow it as you notice friction. Nothing here ships anywhere.

**Precedence.** When the agent reads all three surfaces, the order is: (1) the Gator-managed block, (2) team-shared content outside the sentinels and in `.gator/`, (3) your `*.local.md`. Personal notes may extend behavior but must not override team policy — that keeps team decisions load-bearing across everyone's machines.

## Team-Shared Skills

When a skill benefits more than one person on the team, route it to a tracked surface:

- **Repo-shared entry-point content** — put it above or below the sentinels in `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`. Good for standing instructions the agent should always read at session start.
- **`.gator/procedures/`** — good for team workflows, install recipes, review checklists, deploy runbooks. Travels through normal PR review.
- **`.gator/charters/`** — good for module-level invariants, tripwires, architectural boundaries. The agent reads these before touching related code.
- **User-authored `.claude/commands/`** — good for team-shared slash commands with a UI affordance (short, recallable prompts). Add them, commit them, teammates pick them up on `git pull`. Gator preserves user-authored commands on update — only the four Gator-owned ones (`init`, `update`, `commit`, `loop-join`) get refreshed.

The rule of thumb: **would a teammate cloning this repo tomorrow benefit from seeing this?** If yes, it belongs on a tracked surface. If no, `*.local.md`.

## Team Behavior — Best Practices

From Gator's standpoint, these habits keep the team aligned:

- **Commit vendor tooling to the repo.** Check in `.claude/settings.json`, `.claude/commands/`, `.codex/hooks.json`, `.gemini/settings.json`. Teammates get the same tooling shape on pull.
- **Do NOT commit `.claude/settings.local.json`** (gitignored by default). And don't commit any `*.local.md` — those are per-machine by design.
- **Review Gator refreshes of the managed block like any other diff.** The `.pre-gator-update` sibling backup is your safety net if you had unintended edits inside the sentinels.
- **Prefer `.gator/procedures/` over a slash command** unless the skill needs a slash-invoked UI in the agent tool. Procedures travel through normal PR review; slash commands need to be authored, refreshed, and audited separately.
- **Promote resolved disagreements.** When agents in the team disagree about a workflow, the resolved answer belongs in a procedure or charter — not a personal `*.local.md`. That way the resolution outlives whoever recorded it.

## Recovery Scenarios

**"I edited inside the managed block and `gator update` overwrote it."**
The `.pre-gator-update` sibling file has the previous contents. Open both, keep what you want, delete the backup when you are done.

**"I don't want the four Gator slash commands."**
Delete them from `.claude/commands/`. They will reappear on the next `gator update` because they are Gator-owned. To keep them out for your machine only, add `.claude/commands/init.md`, `.claude/commands/update.md`, `.claude/commands/commit.md`, `.claude/commands/loop-join.md` to your `.gitignore` (but note: teammates who pull will still get them by default — this is only local suppression).

**"I want a totally clean slate."**
Run `gator gatorize` on the same repo. Existing Gator content is refreshed, user content outside the sentinels is preserved, and slash commands you authored yourself are left alone. This is the same command as first install — it detects the existing `.gator/` and takes the upgrade path.

**"I ran `gator gatorize` and don't like the changes."**
`gatorize` installs on your current branch, in place — it does not create a dedicated safety branch on your behalf. The load-bearing clean-undo pattern is to create your own experiment branch **before** running gatorize (`git checkout -b my-gator-experiment`), and delete that branch afterward to fully revert. If you ran gatorize directly on your working branch, its success banner prints a scenario-aware recovery paragraph with git-native recipes for the uncommitted / committed / untracked-files cases.

## See Also

- **[How to Use Gator](how-to-use-gator.md)** — the practical installation and daily-loop guide. See especially the *Working with a Team* section for the three-surface precedence rule (managed block > tracked entry-point content > `*.local.md`) and the *Session Summaries* section for the audit-trail side of team collaboration.
- **[How Gator Works](how-gator-works.md)** — the architectural explainer. The *Multi-Model Review* section explains the enforcer and Gator Loop primitives, which are the team-workflow patterns for cross-model review and governed multi-agent debate.
- **[Command Reference](command-reference.md)** — every `gator` CLI subcommand at a glance.
- **`local-agent-skills.md`** — the same personal-vs-team-shared decision guide from inside a gatorized repo, written for the Architect (the human maintaining the repo's governance layer). Its path depends on your repo's layout: `.gator/.includes/reference-notes/local-agent-skills.md` on the current v2 layout, or `.gator/reference-notes/local-agent-skills.md` on the legacy v1 layout.
