---
message: "Coding loops: modular checkpoints and generation-named artifacts (#55)"
change-type: feature
significance: high
decision-tags: [loop, coding-loop, checkpoints, dashboard, governance]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Revised implementation plan for #55 (coding-loop modular checkpoints), APPROVED at rev 2 (Architect decisions: generation naming for all coding loops and required checkpoints, both approved) (review 2: `/loops` `checkpoint_summary` plus the sidebar card counter, so checkpoint loops never show `Round X/Y`; header and sidebar tests with global findings above the budget; explicit `max_rounds = 2` / extend +1 transition fixture), rev 1, no code changes: `.gator/vault/artifacts/2026-10-05-coding-loop-modular-checkpoints-implementation-plan.md`. It revises the loop-approved round-0 plan per the whiteboard review. Finding 1: artifacts are named by a durable submission generation (`coding.generations` index), which also fixes the legacy post-reopen overwrite. Finding 2: `## Coding Checkpoints` is required for new planning-loop plans (one-checkpoint form for small fixes), with the implicit checkpoint legacy-only, a path-shaped-title guard, and Reviewer quality judgment. Counters are displayed separately (Checkpoint / findings round vs Generation), and D3 adds a full transition table.

- #55 M1 (checkpoint contract): `parse_coding_checkpoints` / `coding_checkpoints_problems` in `loop/submit.py` implement the closed `## Coding Checkpoints` grammar (numbered `N. **Title** — scope. Verify: ...` items, 1-12, plain non-path titles, non-placeholder scope/verify capped at 400 chars, positional ids `cp1..cpN`). New planning sessions carry `contract.coding_checkpoints: 1`; `handle_submit_draft` gates flagged drafts through the #46 capture-once path (`_plan_contract_flags` / `_check_plan_draft`, one combined rejection quoting the one-checkpoint example), legacy sessions unchanged. Plan template, draftor/reviewer guidance (formats pair) and `writing-implementation-plans.md` require the section; charter `scripts-loop.md` updated. Tests: new `tests/test_loop_checkpoints.py` (grammar table, draft-gate table, in-lock authority, template drift guard); new-session fixtures gain the section; contract-shape assertions updated.

- #55 M2 (lifecycle, generation and evidence binding):
  - **Coding start.** `_init_coding_loop` freezes `coding.checkpoints` from the approved-plan bytes using the source session's flag. A flagged source must declare valid checkpoints; a legacy source without the section gets one implicit `Full implementation` checkpoint; an invalid section is refused for both. Refusal is atomic.
  - **State machine.** A non-final checkpoint approval records `accepted`, opens the next checkpoint on that tree and returns to drafting, with no `coding.approval` and no Git mutation. Only the final approval reaches `implementation_approved`. The findings budget is the active checkpoint's `findings_rounds`, and so is the extend guard. Reopen reactivates the final checkpoint, and the `advance_reopened` docstring is corrected.
  - **Generation naming.** Implementation and findings artifacts are named by generation (`len(coding.generations)`) in all coding loops, which fixes the legacy post-reopen overwrite.
  - **Submission binding.** `handle_submit_implementation(checkpoint=)` binds to the active checkpoint, which an implicit manifest may omit. New `gitsnap.diff_trees` gives the exact checkpoint diff, with revisit markers in Commit State. Reviewed Candidate gains checkpoint and generation rows (declared loops only; legacy output is byte-identical).
  - **Events and records.** Events and records carry `generation`, plus checkpoint fields; there is a new non-terminal `checkpoint_approved` event.
  - **Charter.** `scripts-loop.md` updated, with TRIPWIREs "Checkpoint Approval Never Commits" and "Coding Artifacts Are Named by Generation" and the D3 table.
  - **Tests.** `tests/test_loop_checkpoints.py` adds the coding-start table, the D3 transition table, the exact diff and revisit, the `diff_trees` pure read, the legacy reopen fix and the legacy surface. The coding-test source helper defaults to a pre-#55 source, and the brief tests' plans declare one checkpoint.

- #55 M3 (participant guidance):
  - **CLI flag and counters.** `submit-implementation --checkpoint`. For declared checkpoint loops, the status, wait and list commands print "Checkpoint: K of N -- title (findings round r of b)" plus "Generation: g" instead of `Round: X/Y`.
  - **Status JSON** adds `checkpoint`, `checkpoints` and `generation`; the list JSON adds `checkpoint_summary`. All are additive.
  - **Action prompts.** The Draftor prompt names the checkpoint, its scope, verification and base tree, and the `--checkpoint` command. The Reviewer prompt gives the exact checkpoint diff and states that a non-final approval does not authorize a commit.
  - **Command output.** Submit and review output name the checkpoint and generation. A non-final approval prints "No commit yet".
  - **Shared helper.** New `session.checkpoint_summary()` is used by every display surface.
  - **Docs.** The protocol, `loop-artifact-formats.md` and `/loop-join` pairs are updated, covering checkpoints, the two counters, the planning-draftor requirement and the reviewer checkpoint check.
  - **Charters.** `scripts-loop.md` and `scripts-cross-cutting.md` are updated.
  - **Tests.** CLI text and counter tests cover a checkpoint loop with `status.round` 3 > budget 2, which never shows "Round 3/2"; the legacy surface keeps `Round`.

- #55 M4 (Architect inspection):
  - **Status projection.** `coding_status_view` adds `generation`, per-generation `generation` and `checkpoint_id`, and `checkpoints` for declared manifests only (title text; scope and verify are never projected).
  - **`/loops`.** The `/loops` items gain `checkpoint_summary` for checkpoint coding loops only.
  - **Header and sidebar (`loop.js`).**
    - The live and outcome headers show "Checkpoint K of N · findings round r of b" plus a separate Generation item instead of Round.
    - Sidebar cards, active and history, show "Checkpoint K/N · findings r/b · gen g".
  - **Coding region.** It gains Checkpoint and Generation rows and a `.loop-checkpoint-list` progress list: glyph, text and weight, never colour alone.
  - **Labels and fingerprints.** There is a "Checkpoint approved" label, and "(cpK · gen g)" suffixes on timeline cards and artifact toggles, from event fields only. Fingerprints are extended, so identical polls stay mutation-free.
  - **Charters and changelog.** Charters `scripts-dashboard.md` and `scripts-dashboard-ui.md` are updated, and the CHANGELOG has Unreleased Added and Fixed entries for #55.
  - **Tests.** Server: one parameterized test covers checkpoint, legacy-coding and planning loops on `/status` and `/loops`, with `status.round` 3 > budget 2. UI:
    - header and sidebar counters for active, terminal and legacy loops (never "Round" or "3/2");
    - the progress list, labels and suffixes;
    - mutation-free polls with a checkpoint payload.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
