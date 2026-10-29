# Command Reference

All commands use the `gator` CLI installed via `pipx install gator-command`.

## Getting Started

### `gator gatorize <path>`

Install or upgrade governance in a project repo. Creates `.gator/` with constitution, charters, hooks, and knowledge base scaffolding. Installs on your current branch, in place — prints a pre-action summary and asks for confirmation before touching anything. If you want an isolated experiment, create your own branch first (`git checkout -b my-gator-experiment`).

### `gator init`

Type this inside an AI coding session (Claude Code, Codex, Gemini CLI). Displays repo governance status and orients the agent to the project.

### `gator dashboard`

Opens Gator Dashboard in your browser. Fleet view, repo browser, governance settings, version management.

### `gator version`

Shows the installed Gator CLI version.

## Governance

### `gator pulse`

Generates the strategic operations brief (`.gator/pulse.md`) — a summary of project momentum, priorities, and recent activity.

### Commit policy (Dashboard Fleet → Warn)

Each engineer chooses the commit policy for their own clone on their own machine: **strict** (the default) or **warn** (every finding is advisory). Set it with the **Commit policy** dropdown (Strict / Warn) in the Dashboard Fleet view. The setting is stored in Git's private area for that clone (`$(git rev-parse --git-path gator-commit-policy.json)`), never in the repository, so it never changes anyone else's checks. A commit made in warn mode records the trailer `Gator-Commit-Policy: warn`. Enterprise-managed repositories follow Enterprise policy and cannot be changed locally. The tracked `.gator/config.json` `enforcement_level` is no longer read.

## Upgrade

### `pipx upgrade gator-command`

Upgrades the Gator CLI to the latest version from PyPI. Also available from the dashboard Updates view.

Then refresh templates in each governed repo:

```
gator gatorize .
```

## Flags

Most commands support:

| Flag | Effect |
|------|--------|
| `--json` | JSON output instead of formatted display |
| `--dry-run` | Preview without making changes |
| `--path` / `-p` | Specify target repo path |
