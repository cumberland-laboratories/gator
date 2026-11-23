---
date: 2026-11-22
type: decision-record
source: .gator/inbox.md (tracked until #104)
---

# Shared decisions and notes moved out of the inbox

Until #104 the inbox was tracked, so it also held team material:
ratified standards, Architect design decisions and a few unfiled
observations. The inbox is now each person's own notes and is no longer
committed, so that material lives here. Open work is in GitHub Issues
and current priorities are in `roadmap.md`.

## Retention standard for roadmap.md (Architect direction 2026-09-12; ratified 2026-09-14)

- **Current-facing only.** `roadmap.md` holds current strategy,
  priorities and planned work. (The inbox was covered too until #104;
  it is now personal and outside this standard.)
- **No shipped-release narratives; no historical change log.** Git
  history and commit messages are authoritative for what has shipped.
  Durable historical detail moves to focused artifacts under
  `.gator/artifacts/` when it merits preservation; otherwise Git
  carries it.
- **Soft cap: ~250 lines.** Compact or archive before adding past that.
- **Roll-forward pattern:** prepend short notes; do not extend dense
  paragraphs.

First-pass compaction landed 2026-09-14 (roadmap 87% reduction;
historical detail archived at
`.gator/artifacts/2026-09-14-roadmap-shipped-history-archive.md`).
Mechanical soft-cap check is #24.

## Architect design decisions

### Dashboard "Paper" visual direction (Architect preference 2026-10-18)

Static mock-ups applied the Welcome view's narrative style to Fleet,
Commits and Loop, with three sidebar/strip treatments. The Architect
prefers **Paper**: an all-light shell, large type, quiet colour, as simple
as possible. Mock-ups (machine-local):
`vault/artifacts/2026-10-18-dashboard-calm-mockups/index.html`. They draw
on #5 (Loop visual direction), #62, #65, #79 and #80. They are for design
review only and do not yet have an issue or plan.

Guiding principle (Architect, 2026-10-18): **simplicity and minimalism**.
Decisions made during review:
- Page headers: the title only, with no subtitle. The main area is off-white (`gray-50`).
- Running loop: a pulsing mark on the workspace tab and beside Loop in the
  sidebar. A solid dot means Coding and a hollow ring means Planning; the
  shape carries the meaning and the colour (green or amber) is a second cue.
  The sidebar also shows the word.
- Fleet: no summary sentence. One-column sorting on every column.
- Active Loop: no status sentence, no elapsed time, no status ledger (this
  supersedes the #65 ledger idea) and no horizontal checkpoint bars. The
  timeline is newest first and opens with a "Now" line. Beside it, a
  vertical checkpoint list (finished gray, current amber and thicker, upcoming
  light gray) has a light "?" after each name. The "?" opens that
  checkpoint's text from the plan, with its Verify steps.
- Artifacts: rows only. "Approved plan" comes first and opens the rendered
  plan. No cards.
- The "?" text comes from the plan's `## Coding Checkpoints` section. 12 of 13
  approved plans already use it in the same form (numbered, **bold
  title**, `Verify:` line). Plans bound for coding should be required to
  have it (see #69). A plan without it shows an honest "not described
  separately" message.

### Dashboard inspection-workspace decisions (Architect-ratified 2026-09-12)

- **Document tabs**: dropped from current scope. Hands-on use of the
  shipped sidebar navigation showed tabs are unnecessary. Do not
  implement Phase 2 tab strip / tab-descriptor model unless new
  usage evidence creates a concrete need. (Not to be confused with
  #80 **workspace tabs**, 2026-10-16: one tab per repository context
  above the shell. That feature does not revive per-document tabs.)
- **`field-guides/` retirement**: deferred to lowest priority.
  Preserve current behavior; revisit later.

### Loop planning-time heuristic (Architect observation 2026-09-26)

With charters, a draftor needs very little time to research before
it starts the plan. **If that research takes more than about 2
minutes, treat it as a warning sign**: the sketch is too broad, or the
files it touches have no usable charter. In both cases, fix the
cause instead of lengthening the turn.

Evidence from the `precommit-override-lifecycle` loop: each draft
took about 3 minutes, and the plan was approved in round 2. The only
slow part was `gator-pre-commit.py`, `gator-approve.py` and
`precommit_*.py`. These map only to Cross-Cutting in `INDEX.md` and
have no function-level charter. Both rounds of review findings (the
dispatcher route, and the retired `.includes/scripts/` copy) came from
that gap.

Possible future work:
- Add a scoping check at `gator loop start`. It flags sketch paths
  with no charter coverage and sketches that span too many charters.
- Keep escalation for Architect-owned decisions, not for more time.

## Observations without an issue

### Repo sidebar preferences are keyed by display name (2026-10-17, unfiled)

The Repo tree state is now per repository key, but the sidebar width and
collapse preferences (`gator-sidebar-width:<name>` /
`gator-sidebar-collapsed:<name>` in `localStorage`) are still keyed by
display name, so two registered repositories with the same name share
them. The server's `/files`, `/file` and `/search` routes are name-addressed
too. Small; file an issue if duplicate names show up in practice.

### Post-legacy-repo cleanup — deferred, no work item

After the Architect archives the legacy
`cumberland-laboratories/gator-command` GitHub repository, treat the
local standalone clone as reference-only and remove it after the
agreed retention period. Not filed as a GitHub issue because it's
Architect-side housekeeping, not a Gator code change.

## Resolved or filed (2026-11-22)

- **Repo view: a late default-document load can replace a newer HTML
  selection (2026-10-17).** Still present: `loadFile()` in
  `views/repo.js` writes the content pane after `await fetch()` without
  checking the file is still selected. Filed as #111.
- **`gator loop codex` removed Codex's own settings from the managed
  block (2026-10-17).** Fixed by #87: `render_config()` in
  `loop/codex_launcher.py` now moves tables Codex wrote inside the block,
  unchanged, to just above it.
- **Machine state** (local Postgres, Enterprise sandbox paths, machine
  ID) stays in the Architect's personal inbox. It describes one machine
  and includes a local database password, so it is not committed.
