# Gator Init

You were started with `gator init`. This file is Gator's entry point for this
repository. It is short on purpose: it tells you what to read, in what order.
It does not repeat the rules. Each rule has one source, named below.

This file is next to `constitution.md` and `procedures/`. On the current
layout that directory is `.gator/.includes/`; on older layouts it is `.gator/`.
`gator init` prints the exact paths for this repository.

## Before your first response

1. Read `constitution.md` next to this file. It governs how you work here.
2. Read `mission.md`, `roadmap.md`, and `inbox.md` at the `.gator/` root.
   Skip any file that does not exist yet (a fresh repository).
3. If `.gator/charters/` contains only templates, follow `gator-start-up.md`
   next to this file before substantial coding work.

Then follow the constitution's Session Opening section.

## Joining a loop

Read this section only when you were given a loop token (`gator loop join`).

1. Read `procedures/gator-loop-protocol.md` next to this file. It is your
   behavioral contract for the loop.
2. Run `gator loop status --token <your-token>` and act on its output.

Do not read loop material in an ordinary session.

## Native agent files

Gator does not create, edit, back up, or repair `CLAUDE.md`, `AGENTS.md`,
`GEMINI.md`, or similar vendor instruction files. These files belong to the
repository and its users. They may add team or personal guidance. That
guidance can extend Gator governance; it cannot override it.

Older Gator versions wrote a block between `<!-- GATOR:BEGIN -->` and
`<!-- GATOR:END -->` into those files. Gator no longer refreshes that block, so
it can be out of date. If it conflicts with this file or with the
constitution, this file and the constitution apply. The repository owner
decides whether to keep or remove the old block.
