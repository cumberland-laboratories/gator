---
schema-id: gator-commit-summary-v1
kind: markdown-with-yaml-frontmatter
emitter: src/gator_command/templates/gator-starter/scripts/precommit_session.py::write_commit_summary
consumer: Dashboard Audit view (planned), fleet report aggregation
version: 1
---

# gator-commit-summary-v1

## What it is

A per-commit markdown summary written to `.gator/sessions/*.md` by the
post-commit hook. Base Gator emits this on **every** commit — silent,
local, in the governed repo. No user command produces it. No user
command opens it today; the Dashboard's `views/audit.js` code exists
but is not wired into the sidebar. Consumers may appear later.

## File naming

```
.gator/sessions/{YYYY-MM-DD}-{repo_name}-commit-{HHMMSS}.md
```

- `YYYY-MM-DD`: commit date in UTC
- `repo_name`: `gator_dir.parent.name`
- `HHMMSS`: commit time in UTC, zero-padded

Example: `.gator/sessions/2026-07-31-gator-command-commit-142218.md`.

## Frontmatter — required keys

Written in exactly this order by `write_commit_summary` (lines 445–460
of `precommit_session.py`):

| Key | Type | Notes |
|---|---|---|
| `schema` | literal | Must equal `gator-commit-summary-v1`. |
| `type` | literal | Must equal `commit`. |
| `date` | string | `YYYY-MM-DD` UTC. |
| `timestamp` | string | ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`). |
| `repo` | string | Repo directory name. |
| `vendor` | string | First segment of the `agent` value split on `,`. May be empty. |
| `message` | string | Commit message summary line (from `commit_draft.message`, else the commit-msg first line). |
| `change-type` | string | From `Gator-Change-Type` trailer. May be empty. |
| `significance` | string | From `Gator-Significance` trailer. May be empty. |
| `decision-tags` | string | Comma-joined tags from `Gator-Decision-Tags` trailer. May be empty. |
| `agent` | string | From `Gator-Agent` trailer. May be empty. |
| `architect` | string | From `Gator-Architect`, falling back to legacy `Gator-PI`. May be empty. |
| `charter-changed` | string | `"yes"` / `"no"` / empty. |

Legacy accepted:
- `pi:` in place of `architect:` in commit summaries written before the
  Architect rename (accepted by the Contracts test as a valid legacy
  variant).

## Body — required sections (each optional if empty)

```
## Decisions

- <up to 10 decision-tagged or Architect-attributed lines from commit_draft body>

## Session Notes

<up to 30 lines of the raw commit_draft body>

*(N more lines in commit_draft.md)*   ← appended if body was capped
```

`## Decisions` and `## Session Notes` are the only recognized section
headers. Additional H2s must not appear.

## Canonical fixture

See `contracts/compatibility/fixtures/valid_commit_summary.md`.
