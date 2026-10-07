---
message: "Loop: reject junction/reparse-point source-loop directories (#51 follow-up)"
change-type: fix
significance: notable
decision-tags: [loop, security, containment]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- #51 follow-up, source-loop containment hardening (whiteboard finding):
  - **The gap.** A Windows directory junction under `.gator/loops/` is a reparse point but not a symlink, so the `is_symlink()`-only check let it redirect source reads outside the governed loops directory. Per-file checks could not catch it, because the files behind it are ordinary.
  - **The fix.** New `loop/host.py::_require_source_dir(source_dir, loop_id)` rejects a symlinked **or** reparse-point source dir with "Source loop must not be a symlink or reparse point: <id>". It runs before `session.json` or any artifact is opened, and the error never names the redirected target.
  - **Where it applies.** Both `_init_revision_loop` (`--revise-from`) and `_init_coding_loop` (`--from-loop`) call it.
  - **Unchanged:** the canonical-ID, mode, approval, session-lock and atomic-rollback behaviour, and "Source loop not found" for a missing directory.
  - **Tests.** `tests/test_loop_plan_sources.py` adds `test_reparse_point_source_dir_is_refused` (both paths; `_is_reparse_point` mocked for the source dir only). It asserts the exact error, no new loop dir, tokens, session or events, an unmodified source, and that the source session lock is never taken. It also adds `test_symlinked_source_dir_is_refused` (both paths; it skips where directory symlinks cannot be created). A mutation check that restores the `is_symlink()`-only guard fails both reparse tests.
  - **Charter.** In `scripts-loop.md`: the `_init_revision_loop` and `_init_coding_loop` entries, plus the new TRIPWIRE "Source Loop Directories Are Contained".
