# Custom Skills and Team Workflow

A practical guide to what Gator manages, what stays yours, and how teams share AI-coding skills through a Gator-governed repo. Written for prospective adopters and for teammates joining a repo that already has Gator installed.

If you have not installed Gator yet, start with [How to Use Gator](how-to-use-gator.md).

## What Are "Skills" in Agent-Tool Land?

Modern AI coding assistants (Claude Code, Codex CLI, Gemini CLI) all take three kinds of guidance:

- **Slash commands** — short authored prompts you invoke by name in a session (e.g. `/init`, `/review`). Vendors store them under `.claude/commands/`, `.codex/commands/`, or `.gemini/commands/` in the repo.
- **Vendor instruction files** — free-form markdown the tool reads on session start. Vendors call this `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` at the repo root. It sets tone, priorities, and standing rules for the agent.
- **Personal notes** — the same shape as vendor instruction files, but scoped to one person on one machine.

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

Nothing. These files belong to your repository. Gator does not create, edit, back up, refresh, or repair them, on install or on update.

Gator's own entry point lives inside `.gator/`: `GATOR_INIT.md`. A session starts when someone runs `gator init`. Its output names `GATOR_INIT.md` and then the constitution and context files to read. That works the same way in every AI tool, with or without vendor files.

If you want your AI tool to start Gator on its own, add a one-line pointer to your vendor file, for example:

```markdown
At session start, run `gator init` and follow its output.
```

Keep it a pointer. Gator's rules live in `.gator/`; copying them into a vendor file creates a second, drifting copy.

**Repositories gatorized by an older Gator version** may have a block between `<!-- GATOR:BEGIN -->` and `<!-- GATOR:END -->` in these files. Gator no longer refreshes it, so it can go out of date. `gator update` leaves it exactly as it is, and `gator state status` reports it as "historical Gator block (not refreshed)". Where it disagrees with `GATOR_INIT.md` or the constitution, those win. Keep it, trim it to a pointer, or remove it — your choice, in a normal commit.

## Personal Skills, Per-Machine — the `*.local.md` Companion

Sometimes you want personal notes that are just for **you on this machine** — not for the team and not for review.

Create a companion file at the repo root (the vendor file itself is optional):

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

**Precedence.** When the agent reads all three surfaces, the order is: (1) Gator governance in `.gator/` (`GATOR_INIT.md`, the constitution, charters), (2) team-shared content in your vendor files and `.gator/procedures/`, (3) your `*.local.md`. Team content and personal notes may extend behavior but must not override Gator governance, and personal notes must not override team policy — that keeps team decisions load-bearing across everyone's machines.

## Team-Shared Skills

When a skill benefits more than one person on the team, route it to a tracked surface:

- **Your vendor files** — `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`. Good for standing tool-specific instructions the agent should always read at session start. Gator never edits them.
- **`.gator/procedures/`** — good for team workflows, install recipes, review checklists, deploy runbooks. Travels through normal PR review.
- **`.gator/charters/`** — good for module-level invariants, tripwires, architectural boundaries. The agent reads these before touching related code.
- **User-authored `.claude/commands/`** — good for team-shared slash commands with a UI affordance (short, recallable prompts). Add them, commit them, teammates pick them up on `git pull`. Gator preserves user-authored commands on update — only the four Gator-owned ones (`init`, `update`, `commit`, `loop-join`) get refreshed.

The rule of thumb: **would a teammate cloning this repo tomorrow benefit from seeing this?** If yes, it belongs on a tracked surface. If no, `*.local.md`.

## Team Behavior — Best Practices

From Gator's standpoint, these habits keep the team aligned:

- **Commit vendor tooling to the repo.** Check in `.claude/settings.json`, `.claude/commands/`, `.codex/hooks.json`, `.gemini/settings.json`. Teammates get the same tooling shape on pull.
- **Do NOT commit `.claude/settings.local.json`** (gitignored by default). And don't commit any `*.local.md` — those are per-machine by design.
- **Review `gator update` diffs like any other change.** They touch only `.gator/` content, hooks, and vendor settings — never your `CLAUDE.md` / `AGENTS.md` / `GEMINI.md`.
- **Prefer `.gator/procedures/` over a slash command** unless the skill needs a slash-invoked UI in the agent tool. Procedures travel through normal PR review; slash commands need to be authored, refreshed, and audited separately.
- **Promote resolved disagreements.** When agents in the team disagree about a workflow, the resolved answer belongs in a procedure or charter — not a personal `*.local.md`. That way the resolution outlives whoever recorded it.

## Recovery Scenarios

**"My `CLAUDE.md` still has an old `<!-- GATOR:BEGIN -->` block."**
An older Gator version wrote it. It is no longer refreshed and may be out of date. Keep it, replace it with a one-line `gator init` pointer, or delete it in a normal commit — Gator will not touch it either way.

**"I don't want the four Gator slash commands."**
Delete them from `.claude/commands/`. They will reappear on the next `gator update` because they are Gator-owned. To keep them out for your machine only, add `.claude/commands/init.md`, `.claude/commands/update.md`, `.claude/commands/commit.md`, `.claude/commands/loop-join.md` to your `.gitignore` (but note: teammates who pull will still get them by default — this is only local suppression).

**"I want a totally clean slate."**
Run `gator gatorize` on the same repo. Existing Gator content in `.gator/` is refreshed, your vendor files are left alone, and slash commands you authored yourself are left alone. This is the same command as first install — it detects the existing `.gator/` and takes the upgrade path.

**"I ran `gator gatorize` and don't like the changes."**
`gatorize` installs on your current branch, in place — it does not create a dedicated safety branch on your behalf. The load-bearing clean-undo pattern is to create your own experiment branch **before** running gatorize (`git checkout -b my-gator-experiment`), and delete that branch afterward to fully revert. If you ran gatorize directly on your working branch, its success banner prints a scenario-aware recovery paragraph with git-native recipes for the uncommitted / committed / untracked-files cases.

## See Also

- **[How to Use Gator](how-to-use-gator.md)** — the practical installation and daily-loop guide. See especially the *Working with a Team* section for the three-surface precedence rule (Gator governance in `.gator/` > team vendor files > `*.local.md`) and the *Session Summaries* section for the audit-trail side of team collaboration.
- **[How Gator Works](how-gator-works.md)** — the architectural explainer. The *Multi-Model Review* section explains the enforcer and Gator Loop primitives, which are the team-workflow patterns for cross-model review and governed multi-agent debate.
- **[Command Reference](command-reference.md)** — every `gator` CLI subcommand at a glance.
- **`local-agent-skills.md`** — the same personal-vs-team-shared decision guide from inside a gatorized repo, written for the Architect (the human maintaining the repo's governance layer). Its path depends on your repo's layout: `.gator/.includes/reference-notes/local-agent-skills.md` on the current v2 layout, or `.gator/reference-notes/local-agent-skills.md` on the legacy v1 layout.
