<!--
Fleet-repo /init skill (shipped in the gator-starter template).

Deployed to `.claude/commands/init.md` in every gatorized repo.

Note: the source `gator-command` monorepo keeps an intentionally divergent
copy at its own `.claude/commands/init.md`. Do not "sync dogfood copies"
from this template into the source repo — the source repo has a one-off
setup (root constitution, source charters under `gator-command/charters/`)
that this fleet template does not describe.
-->

Run the Gator boot sequence by executing: `gator init` (requires the Gator CLI — `pipx install gator-command`; pre-2.9 repos may still carry a runnable `gator-init.py` in `.gator/scripts/` or `.gator/.includes/scripts/`).

Display the output exactly as printed — do not summarize, reformat, or interpret it. This is the standardized Gator orientation display.

After displaying the output, read these files in order. This is your governance contract — do not skip step 1.

1. **The constitution.** Find `constitution.md` in `.gator/` or `.gator/.includes/`, whichever exists, and read it. This defines how you work in this repo.
2. **The cross-cutting charter.** Find `cross-cutting.md` under `.gator/charters/` or `.gator/.includes/charters/`, and read it. It documents multi-module invariants that break silently when violated. Skip only if the charter set is empty (fresh bootstrap state).
3. **The charter INDEX.** Find `INDEX.md` under `.gator/charters/` or `.gator/.includes/charters/`, and read it. It maps code paths to the charter you need to read before changing them. Skip only if the charter set is empty.
4. `.gator/mission.md` (what this repo is building — skip if absent on a fresh repo)
5. `.gator/roadmap.md` (current priorities — skip if absent on a fresh repo)
6. `.gator/inbox.md` (anything captured since last session — skip if absent)

Then greet the Architect and surface the most relevant next step, as described in the constitution's session-opening procedure.

**Do not read `.gator/commit_draft.md`** — it is gitignored and reset after every commit, so at session open it is effectively always the empty stub. It exists as commit-message plumbing, not a session-opening surface.
