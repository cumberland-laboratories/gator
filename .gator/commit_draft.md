---
message: "Loop: coding mode with diff-aware implementation review (#41) + Dashboard polling fix (#44 core)"
change-type: feature
significance: high
decision-tags: [loop, coding-mode, git, dashboard, governance]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- #41 coding loop, Module 2 (Git snapshot helper; approved plan copied to `.gator/vault/artifacts/2026-10-01-coding-loop-diff-aware-review-implementation-plan.md`): new `src/gator_command/scripts/loop/gitsnap.py`. It provides `snapshot(worktree_root, base_head)`, which returns raw, unfiltered Git facts or an explicit error code.
  - Facts: worktree root, HEAD and its tree, detached/branch, the staged-tree OID from `write-tree`, changed paths against the base (with renames), and unstaged/untracked residue.
  - Error codes: `git_unavailable`, `not_a_repo`, `bare`, `unborn`, `conflict`, `bad_base`, `git_busy` (an index lock is retried once), `git_error`.
  - Path lists are capped at 1000, with counts of what was truncated. It never modifies refs, the index or the worktree.
- New `tests/test_loop_gitsnap.py` (20 tests, all on real temp repos isolated by `GIT_CEILING_DIRECTORIES`): clean, staged-vs-base, branch moved, rename, residue vs ignored, subdirectory, detached, linked worktree, path cap, unborn, conflict, bad base, bare, not a repo, missing path, Git missing, the busy retry and its recovery, no mutation, and malformed parse records.
- `pyproject.toml` package-data now includes `gitsnap.py`.
- Module 2 review fix (whiteboard P2): a non-directory `worktree_root` (for example an existing file) is rejected as `not_a_repo` before any Git invocation. `_invoke()` classifies launch failures: `git_unavailable` only when Git itself cannot run, `not_a_repo` for a bad cwd, `git_error` for any other OSError. Added 3 regression tests (23 total), each verified to fail on the pre-fix code.
- `scripts-loop.md`: Covers/Owns, a `snapshot()` entry with a field/command table, and the new TRIPWIRE "Raw Staged Tree Is Review Authority".
- #41 Module 1 (mode, stage table, guarded start, reopen):
  - `session.py`: `loop_mode()` is the only mode reader. Missing, `planning` and the legacy `planning-only` (still written for planning loops, so planning residue is byte-identical) all mean planning; an unknown mode fails closed. `create_session(mode=, coding=)` builds coding sessions.
  - `state_machine.py`: one mode-indexed `STAGES` table and `stages_for()`. The categorizers, mode-indexed model action rules (`submit_implementation`), unblock stage/role validation, and the extension resume target (`implementation_revision` for coding) all read it. New Architect `reopen` action and `advance_reopened()`. `ALL_STAGES` keeps its planning meaning; `CODING_ALL_STAGES` and `EVERY_STAGE` are added.
  - `host.py`: the guarded successor `init_loop(mode="coding", from_loop=)` / `_init_coding_loop()`:
    - a canonical id check;
    - a source check under its session lock (planning, `plan_approved`, non-empty plan);
    - a Git base from `gitsnap`;
    - an `approved-plan.md` copy plus a SHA-256 re-read check;
    - atomic cleanup of a partial directory.

    `reopen_loop()` holds `start.lock` and enforces the single-active-loop rule. Timeout enforcement and `find_active_loop` are mode-aware.
  - `submit.py`: `handle_reopen()`. `events.py`: `loop_reopened`.
  - `cli.py`: `start --mode/--from-loop` and the `reopen` command. `_attach_foreground_watcher()` is the host contract shared with `extend`. Status gains a coding prompt, `mode` in JSON, and the approved-commit handoff text.
  - `liveness.py` now uses the mode-aware categorizers.
  - Dashboard `_adopt_orphaned_loops()` uses `is_terminal()` instead of a hard-coded stage list.
- Module 1 review fix (whiteboard P1): source loop ids must be canonical. The id regex must start and end alphanumeric (rejecting the Windows trailing-dot alias), and under the source session lock the requested id must equal the source session's own `loop_id`. That also rejects case-variant aliases, which resolve to the same directory on Windows (found while fixing). Added 7 regression tests; the aliases were verified to be accepted by the pre-fix code.
- Tests: new `tests/test_loop_coding_mode.py` (92). The planning suite is unchanged, at 299. Also fixed a Windows flake in `test_requires_anti_csrf_header` (#36) by sending no body.
- Charters: `scripts-loop.md` (new and updated entries; Resumable Terminal Stage and Stage-Role tripwires extended for coding), `scripts-dashboard.md` (mode-aware adoption).
- #41 Module 3 (implementation submission):
  - `state_machine.advance_implementation_submitted()`.
  - `submit.handle_submit_implementation()`:
    - checks the required headings before the lock;
    - under the session lock, takes a raw `gitsnap` snapshot against the captured base, requires something staged, and writes `implementation.round-N.md` / `.current.md` with a CLI-owned Commit State section;
    - persists the raw snapshot generation and emits `implementation_submitted`.
  - Helpers: `missing_implementation_headings`, `render_commit_state` (exact-candidate review command `git diff <base_tree> <staged_tree>`; fenced, injection-safe path lists), `replace_commit_state`, and `split_residue`.
  - `split_residue` is a display-only split of residue into loop residue (`.gator/loops/`) and other residue, so the warning fires only for real residue. Raw facts are unchanged.
- Module 3 review fix (whiteboard P2): an implementation artifact must have exactly one level-2 `## Commit State` outside code fences (`commit_state_heading_count`). Duplicates are rejected before the lock, and `replace_commit_state` also refuses them, so the stored artifact always has a single CLI-owned state block. Added 3 regression tests; the duplicate cases were verified to fail on the pre-fix code.
- New CLI `gator loop submit-implementation`. The Reviewer's coding status shows the candidate tree and the review command. New `implementation_submitted` event label.
- Tests: new `tests/test_loop_coding_submit.py` (28). The `test_loop_coding_mode.py` fixture now writes its sketch outside the repo, so it is not residue.
- `scripts-loop.md`: handler, transition, helpers and CLI entries; subcommand counts.
- #41 Module 4 (review, approval binding, resolution):
  - `state_machine.advance_implementation_reviewed()` and the pure `resolve_approval()`, which returns committed / pending / stale (with a reason) / unknown / none / invalidated.
  - `submit.handle_submit_review()` gains a `loop_dir` argument and a coding path, `_coding_review()`:
    - the review binds to the latest generation's submitted candidate;
    - APPROVE requires the live staged tree and HEAD to still match (or the live check to succeed);
    - findings are always accepted and flagged `candidate_changed`, so the loop can't deadlock in review;
    - a CLI-owned `## Reviewed Candidate` section is appended, and an author-written one is rejected;
    - the review is recorded on the generation and the approval as `{tree, head, round, ts}`.
  - `events`: `implementation_approved` (terminal event and label).
  - `cli`:
    - status, wait and architect status print the live approval resolution with text markers, plus a reopen hint for stale or unknown; JSON gains `approval_resolution`;
    - `submit-review` gives a coding-specific handoff message.
- Tests: new `tests/test_loop_coding_review.py` (26):
  - pure resolution matrix and transition rules;
  - end to end: approval then commit resolves Committed; a changed candidate blocks approval but not findings; HEAD moved; an unverifiable live state; post-approval drift goes Stale, then reopen, resubmit and approval; multi-round revision; a hook-like commit is Stale; author-written Reviewed Candidate rejected; max rounds then extend; watcher exit plus a terminal notification;
  - CLI restart recovery and Architect stale/reopen hints.
- `scripts-loop.md`: entries for the transition, resolution, coding review path and status resolution; a `TERMINAL_EVENTS` note.
- #41 Module 5 (Dashboard):
  - Server:
    - the status poll serves the slim `submit.coding_status_view()` instead of the raw coding binding (no path lists);
    - new Architect-only `GET /loops/<id>/snapshot` (no-store): the live `resolve_approval()` result plus slim facts, 409 for planning loops;
    - `POST /reopen` mirrors `/extend` (`reopen_loop`, then `_ensure_loop_watcher(retry=True)`, with honest watcher reporting);
    - the coding artifacts are allowlisted.
  - UI (`loop.js` / `dashboard.css`):
    - a `#loop-region-coding` panel with candidate facts, the review verdict and a residue note;
    - a live resolution banner for approved coding loops, using text plus glyph plus weight: ✓ Committed, ● Pending, ⚠ Stale (reason), ? Unknown;
    - a Reopen-for-revision inline form (required reason; survives polling);
    - coding stage labels and badges, `implementation_approved` as terminal, coding artifacts and event labels;
    - approved coding loops keep polling.
  - Polling ownership: `ensurePolling()` is now the only interval creator, at mount and on selection. Selecting a live loop after a terminal one resumes polling; this is the core of #44. It also fixes a leaked second interval that the existing `test_terminal_loop_stops_polling` caught.
- Tests:
  - new `tests/test_dashboard_loop_coding.py` (19): the projection has no raw lists or tokens; artifact allow and deny; snapshot pending, committed, stale, unknown, planning 409 and Architect authority; reopen anti-CSRF, message, stage, success with watcher, single-active;
  - new `tests/test_dashboard_ui/test_loop_coding_ui.py` (6 Playwright): facts and artifacts; pending then committed while polling; stale reopen flow with the form surviving polls and the POST shape; unknown; zero-mutation polls; the #44 polling restart (verified to fail without the fix).
- Charters: `scripts-dashboard.md`, `scripts-dashboard-ui.md`, `scripts-loop.md`.
- #41 Module 6 (protocol and docs):
  - `procedures/gator-loop-protocol.md` (both copies) gains a new "Coding Loops (Implementation Review)" section:
    - the staged tree is the candidate;
    - Draftor steps: stage the charter and `commit_draft` changes, no commits, `submit-implementation` and its required sections;
    - Reviewer steps: the exact `git diff <base_tree> <staged_tree>`, no `## Reviewed Candidate`, approval refused on a changed candidate;
    - the one-normal-commit handoff, the PENDING / COMMITTED / STALE / UNKNOWN meanings and Architect `reopen`;
    - a coding state table with its category summary; the quick reference is updated.
  - `reference-notes/loop-artifact-formats.md` (both copies): implementation artifact template and rules.
  - `/loop-join` (both copies): coding-loop steps.
  - The vendor-neutral entry paragraph is unchanged.
- CHANGELOG `[Unreleased]`: #41 added, and #44 (core) fixed.
- `tests/test_loop.py` gains two drift guards: the coding state table must match `CODING_ALL_STAGES` and the mode table, and the implementation template must match `IMPLEMENTATION_HEADINGS` with exactly one Commit State.
- `scripts-loop.md`: Cross-Vendor Orientation covers the coding docs and their pins.
- `scripts-cross-cutting.md`: the package-data rule now also names `scripts/loop/gitsnap.py` (#41), which `pyproject.toml` lists.
- Dashboard POST reliability: `_check_post_auth()` now drains a rejected request's body (bounded at 1 MiB) before sending 403. Unread request data made Windows reset the connection, which caused intermittent `ConnectionAbortedError` in `test_dashboard_remove` and the #36 liveness test. New `test_rejected_post_with_body_is_delivered_reliably` (40 POSTs) failed 2 of 3 runs against the pre-fix server and passed 5 of 5 with the fix. `scripts-dashboard.md` documents it.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
