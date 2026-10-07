---
message: "Constitution: session snippets are expected residue, never chased"
change-type: governance
significance: routine
decision-tags: [governance, constitution, agent-guidance]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- **Constitution, "Expected governance residue" note.** It now says that every commit emits one new `.gator/session-snippets/*.json`, that a leftover snippet is swept up by the next real commit, and that agents must never stage, commit or report one on its own. It links to `procedures/committing-gator-files.md` §2d, which already held the rule but was one link deeper than agents read.
  - **Copies:** both are byte-identical, `.gator/.includes/constitution.md` and the shipped `src/gator_command/templates/gator-starter/constitution.md`.
  - **Why:** agents kept proposing housekeeping commits just to collect snippets, an endless loop, because each commit emits the next snippet.
- **CHANGELOG `[Unreleased]`:** a Changed entry for this, plus catch-up entries for work committed since 2.22.0 without one:
  - Added: #51 Architect plans and revision planning loops;
  - Added: #53 durable pauses and escalations;
  - Security: the #51 follow-up junction/reparse source-dir containment (`8037b53`).
- **Verification:** template sync, drift and shipped-template audit pass (25), and every test file that references the constitution passes (530).
