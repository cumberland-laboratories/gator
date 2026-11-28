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
  artifacts/
  vault/
  sessions/
  procedures/
  .includes/
```

No root folder holds a `_template.md` (#109). `charters/`, `artifacts/`,
`procedures/` and `blueprints/` carry a `README.md`; `blueprints/` also
carries the two blueprint HTML templates.

## On-demand directories (#109)

These are **not** created by the install. They appear at `.gator/` root
the first time someone puts content in them:

```
.gator/
  threads/
  active-threads/
  policies/
  field-guides/
  reference-notes/     (your own notes; Gator's shipped notes are in .includes/)
```

Each one's `README.md` and `_template.md` ship in `.gator/.includes/<folder>/`,
the place an agent starts from when it creates the folder. Tooling must
treat every on-demand directory as optional.

## Required directories inside `.includes/`

```
.gator/.includes/
  reference-notes/
  procedures/
  charters/
  artifacts/
  threads/
  policies/
  field-guides/
```

Additional shipped content (constitution.md, gator-start-up.md,
.charterignore) lives inside `.includes/` after gatorize. Every folder's
authoring template is `.gator/.includes/<folder>/_template.md`, and each
on-demand folder's `README.md` is next to it (#109). This contract does not
require any other specific file inside `.includes/`; the shipped content
evolves. (`scripts/` left this list with the runtime split, 2026-08-19.)

## Required stub files at `.gator/` root

Written by `write_stubs()` on install if missing. All are user-editable:

| File | Purpose | Initial content |
|---|---|---|
| `mission.md` | Product / project mission | Stub prompt |
| `roadmap.md` | Priority-ordered work | Status key stub |
| `inbox.local.md` | Personal notes (gitignored; a path no commit tracks, #104 / #113) | Empty header |
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
