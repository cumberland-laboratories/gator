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

### `gator enforce`

Manage enforcement level for a repo (strict, warn, off). Also configurable from the dashboard Fleet view.

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
