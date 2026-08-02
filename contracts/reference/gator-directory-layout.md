---
contract-id: gator-directory-layout
kind: reference
owner: base Gator
tested-by: contracts/compatibility/test_gator_layout.py
layout-version: v2
---

# `.gator/` Directory Layout (v2)

## What this contract governs

The **minimum shape** of a governed repo's `.gator/` directory
immediately after `gator gatorize` (or `gator init` on a fresh install).
Fleet tooling, hooks, the Dashboard, and Enterprise integrations all
rely on this shape being present.

Definitive writer: `action_install_gator()` in
`src/gator_command/scripts/gatorize.py:169`, with stubs written by
`write_stubs()` in the same module (line 296).

## Layer split

**User-authored content** lives at `.gator/` root.
**Shipped Gator-native content** lives at `.gator/.includes/`.

## Required directories at `.gator/` root

```
.gator/
  charters/
  blueprints/
  docs/
  threads/
  artifacts/
  vault/
  policies/
  field-guides/
  sessions/
  procedures/
  .includes/
```

## Required directories inside `.includes/`

```
.gator/.includes/
  reference-notes/
  procedures/
  scripts/
```

Additional shipped content (constitution.md, gator-start-up.md,
.charterignore, hook installers) lives inside `.includes/` after
gatorize. This contract does not require any specific file inside
`.includes/` beyond the three directories; the shipped content evolves.

## Required stub files at `.gator/` root

Written by `write_stubs()` on install if missing. All are user-editable:

| File | Purpose | Initial content |
|---|---|---|
| `mission.md` | Product / project mission | Stub prompt |
| `roadmap.md` | Priority-ordered work | Status key stub |
| `inbox.md` | Zero-friction capture | Empty header |
| `identity.md` | Operator identity + operating mode | Frontmatter + Basics section |
| `issues.md` | Active bugs / blockers | Status key stub |
| `commit_draft.md` | Commit message plumbing | Empty frontmatter + Session Change Log heading |
| `patterns.md` | Recurring patterns | Empty header |
| `whiteboard.md` | Ephemeral enforcer surface | `No findings.` |
| `commit_issues.md` | Recent commit findings | `No findings.` |
| `lint-allow.json` | Ignore-list for the charter linter | `[]` |
| `config.json` | Repo-scoped config | `{"enforcement_level": "strict"}` |
| `charters/INDEX.md` | Charter router table | Header + empty row |
| `sessions/.gitignore` | Excludes `_active/` from git | `_active/` |
| `vault/.gitkeep` | Keeps the (gitignored) vault dir | empty |

## Required layout-version marker

```
.gator/layout-version.json
```

Contents: `{"layout": "v2"}`. Presence of this file is the canonical
signal that a repo is on the v2 layout. Its absence means legacy v1
layout (user content and shipped content intermixed at `.gator/` root).

## Required install-metadata marker

```
.gator/.gator-version
```

Line-oriented `key: value` file with keys:
`generation`, `installed`, `updated`, `action`, `installer`, `cli-version`.
Written by `write_gator_version(gator_dir, action)` in `gator-update.py`.

## What this contract does NOT govern

- Contents of `sessions/` beyond the `_active/`-excluding `.gitignore`
  (per-commit summary files are governed by
  `gator-commit-summary-v1`).
- Contents of `session-snippets/` (per-commit snippets are governed by
  `gator-session-snippet-v2`; the directory is created on first
  snippet emission, not by gatorize).
- Presence or absence of `.gator/enterprise.json` (governed by
  `contracts/schemas/enterprise-config.json` and
  `presence-detection.md`).

## Extension rule

Adding a new required directory or stub file to the base install
requires updating this contract AND the pytest that validates it in
the same commit.
