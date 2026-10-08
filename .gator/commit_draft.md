---
message: "Gator-native entry point: GATOR_INIT.md bootstrap; stop managing CLAUDE.md/AGENTS.md/GEMINI.md"
change-type: feature
significance: architectural
decision-tags: [entry-point, gatorize, update, state, init, layout, loop]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Checkpoint 1 (bootstrap contract and handoff):
  - New shipped `GATOR_INIT.md`: the template copy plus a byte-identical dogfood copy in `.gator/.includes/`. It is a short, tool-neutral entry document. It points to the constitution, the session context, the loop protocol (only when a loop token is given) and the native-file ownership statement, and it restates no protocol rules.
  - `gator_layout.py` (both copies): `GATOR_INIT.md` is added to `SHIPPED_ROOT_FILES`, and `GatorPaths.bootstrap` is added. It resolves next to the constitution (`.includes/` on v2). A v2 repo without the file stays v2.
  - `gatorize.action_install_gator` and `gator-update.TEMPLATE_FILES` (both copies) place it at the shipped location. `gator update` adds it to repos that predate it and refreshes it idempotently.
  - `gator init` (both copies): `session_opening_reads()` is the single source for the read order: `GATOR_INIT.md` first when present, then the constitution, then mission/roadmap/inbox.
    - A legacy repo keeps the old two-step handoff plus a `gator update` hint, and `gator init` never creates the file.
    - `--json` gains an additive `session_opening` object.
  - Charters: layout, repo-lifecycle, installer, repo-update and cross-cutting.
  - Tests: `TestBootstrapResolution` (`test_layout.py`), `TestFreshInstallBootstrap` (`test_gatorize.py`), and `TestSessionOpeningHandoff` and `TestGatorInitDocument` (`test_init.py`).
- Checkpoint 2 (native-neutral install and update):
  - `gatorize` no longer calls the retired `action_install_entry_points()` (create/refresh/legacy-upgrade, the foreign-file backup-append-overwrite prompt, `*_ROLLBACK.md`). The pre-action summary now says `CLAUDE.md / AGENTS.md / GEMINI.md` are left untouched. `entry_points.py` keeps only the renderer and legacy upgrade, which `gator state` still uses until checkpoint 3.
  - `gator update` (both copies) drops the Stage 4b entry-point plan/execute pair, its import guard and the template copy's inlined managed-block helpers. `.pre-gator-update` backups are gone. `updated:` gates on overlay changes only. `gator-update-v1` JSON keeps `entry_point_actions: []` and its summary count `0`.
  - Charters: installer and repo-update (new "Native Agent Files Are Repository-Owned" TRIPWIREs).
  - Tests:
    - `TestGatorizeLeavesNativeFilesUntouched` runs the real `gatorize.main()` under `--yes` with an empty stdin over foreign, sentinel, legacy and corrupted native files, and over a repo with none.
    - `TestUpdateLeavesNativeFilesUntouched` runs both update copies as a subprocess.
    - Removed `tests/test_update_entry_points.py`, the Stage 4b parity/AST layers and the install-prompt/cancel-hint pins.
- Checkpoint 3 (state boundary and renderer retirement):
  - `gator state` moves to schema `gator-state-v2`.
    - `status` drops `entry_points` / `entry_point_baseline_kind` and reports informational `native_files` (`present`, `managed: false`, `historical_gator_block`, `local_companion`). Native files are never called drift, missing or in need of repair.
    - `repair` becomes a no-write compatibility stub (same arguments, exit 0).
    - Constitution drift and the version diagnostic are unchanged.
  - `gatorize/entry_points.py` is deleted. Loop-join and Executive Summary guidance now lives only in the protocol, `/loop-join` and the `GATOR_INIT.md` pointers. `managed_block.py` stays as a read-only parsing library.
  - `cli.py`: the `state` help text is updated.
  - Charters: managed-state (rewritten), installer, cross-cutting (records the `gator-state-v2` bump and the retired participant surfaces), loop (cross-vendor orientation) and layout.
  - Tests:
    - `tests/test_state.py` is rewritten: `TestStatusV2`, `TestRepairStub` (no writes for every argument form) and a never-open guard for `*.local.md`.
    - `TestWaitHandoffAlignment` / `TestExecutiveSummaryProducerPaths` no longer pin the renderer or this repo's live CLAUDE/AGENTS/GEMINI files, which keep their exact bytes.
    - Removed the renderer and legacy-upgrade unit tests.
- Checkpoint 4 (explicit-start adoption):
  - The Dashboard loop-join prompt gains the pointer "New to Gator in this repo? Run `gator init` first; its handoff names GATOR_INIT.md and the loop protocol."
  - The docs inventory was re-run; the only new hit was `GATOR_INIT.md` itself. Every "Revise" surface is updated: README; docs `how-to-use-gator`, `architecture` and `custom-skills-and-team-workflow`; and the starter `enforcer-review`, `enforcer-configuration`, `concierge-responses`, `local-agent-skills`, `what-gator-requires-from-a-model`, `gator-version-drift` and `knowledge-capture`, with byte-identical dogfood copies.
  - `CHANGELOG.md` `[Unreleased]`: Added / Changed / Removed / Migration notes.
  - Charters: dashboard (join-prompt pointer).
  - Tests:
    - New `tests/test_native_file_guidance.py` (the retired-claim guard over maintained surfaces, with CHANGELOG and research documents excluded by name, plus template↔dogfood parity for the revised pairs);
    - `test_prompt_names_explicit_gator_init_start`;
    - the session-opening smoke test (gatorize a repo without native files, then `gator init` names `GATOR_INIT.md` first).
