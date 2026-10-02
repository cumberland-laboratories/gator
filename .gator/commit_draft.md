---
message: "Loop: Architect brief at creation (#43) + Context Checked plan evidence (#46)"
change-type: feature
significance: high
decision-tags: [loop, brief, context-evidence, dashboard, governance]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- Implementation plan for #43 and #46 (Architect brief and context evidence), rev 7 (the Dashboard keeps the keep/drop control for a corrupt source brief, with a guarded source-status fetch), rev 6 (Architect decisions: Context Checked on every draft, flexible coding-start brief options keep/drop × new/none with a recorded decision, charter-map deferred, 32 KiB), rev 5 (a neutral `absent` state for no-brief loops, hidden everywhere), rev 4 (brief status view positionally bound to its expected filename), rev 3 after plan re-review (strict brief status serializer; byte-counter wording), rev 2 after plan review: Dashboard coding start (M2a), a fixed-name containment-checked verifier, a separate source-brief integrity check, UTF-8 byte counting, and race-safe captured-bytes validation; no code changes: `.gator/vault/artifacts/2026-10-01-loop-architect-brief-context-evidence-implementation-plan.md`.
- #43/#46 M1 (brief persistence and CLI start; plan rev 7 approved):
  - `session.py`: brief constants (32 KiB cap) and `validate_brief_bytes`, `brief_bytes_from_text`, `read_brief_file`, `brief_meta`.
    - `verify_brief` uses a fixed expected name and checks containment, symlinks and reparse points. Its results are absent / ok / missing / mismatch / unreadable / invalid_ref / unsafe, and it never returns content.
    - Also new: `read_verified_brief`, and the strict, positionally bound `brief_status_view`.
    - `create_session(brief=)` writes metadata only. Planning sessions get the `contract.context_evidence` migration flag.
  - `host.py`: `init_loop(brief_path=, brief_text=, source_brief=)`.
    - The brief is validated before any directory exists, then written read-only and re-verified, with only its sha and size in the start event.
    - Planning starts are now atomic: partial directories are cleaned up.
    - Coding successors implement the Architect's keep/drop × new/none choice. `keep` verifies and copies the source brief, or is rejected atomically with a drop hint. `drop` never opens it. `source_brief_decision` (kept / dropped / none_available) is recorded in the session and event.
  - `cli.py`: `start --brief FILE` and `--source-brief keep|drop` (coding only).
- M1 review fix (whiteboard M1-1): `read_brief_file` now refuses Windows reparse points / junctions, not only symlinks, before any `exists` / `stat` / `open`, matching `verify_brief`. Three tests were added: a real unprivileged directory junction (Windows), the guard running before any file open, and an atomic start rejection. All three were verified to fail without the guard. Per review, the ordering test also asserts that no link-following `stat` runs before refusal; this was verified to fail with a misordered `exists()` probe.
- New `tests/test_loop_brief.py` (54 passed, 2 symlink cases skipped on this Windows account):
  - validation, including the multi-byte byte boundary;
  - every verifier result and every invalid_ref variant;
  - strict and positional status view;
  - planning start shape, immutability, event and atomic rejections;
  - all four coding arrangements, a corrupt source (bytes, missing, swapped ref) failing atomically under keep and succeeding under drop, and CLI argument rejection.
- `scripts-loop.md`: a brief entry, updated create_session / init_loop / coding-successor / CLI entries, and a new TRIPWIRE "Architect Brief Is Immutable Residue, Not a Channel".
- #43/#46 M2 (participant visibility):
  - CLI status (model and Architect) shows labeled brief paths with integrity markers, a "do not rely on it" / escalate note for failures, and the dropped-planning-brief line. Absent briefs print nothing; JSON is additive.
  - Dashboard server:
    - `/status` adds the strict positionally bound `brief` view and `brief_check` (not through the generic allowlist);
    - `coding_status_view(coding, loop_dir)` adds `source_brief`, `source_brief_check` and `source_brief_decision`;
    - the artifact allowlist gains both brief files;
    - the `/prompt` pointer line appears only when a brief exists;
    - `POST /loops/start` accepts an optional `brief` string, validated before locking, and `init_loop` validation errors are now 400.
  - Dashboard UI: the create form gets a brief textarea with a UTF-8 byte counter (`TextEncoder`); over-limit disables Create; blank briefs are omitted. Brief artifact entries sort first with text integrity labels, and invalid or dropped cases are text-only notes. Identical polls cause zero mutations.
  - `dashboard.css`: brief styles.
- Tests:
  - new `tests/test_dashboard_loop_brief.py` (24): start with brief, absent, rejections, and the exact multi-byte limit; injected `content` / `path` / extra never served; swapped and malformed refs give null plus invalid_ref; mismatch and missing; the generic-allowlist pin; the coding source projection with injection, swap and dropped; artifact serving; the prompt pointer; CLI status markers and labels;
  - new `tests/test_dashboard_ui/test_loop_brief_ui.py` (7 Playwright): ok, mismatch, invalid (no fetch), absent (nothing), coding kept and dropped, zero-mutation polls, and the byte counter plus POST shape;
  - `test_dashboard_loop_coding.py`: the coding-projection key pin now includes the source-brief fields.
- Charters: `scripts-dashboard.md` (strict brief status, start brief, artifact allowlist, prompt pointer, plus a note on the pre-existing same-second loop-id collision); `scripts-dashboard-ui.md` (brief UI); `scripts-loop.md` (CLI brief lines, coding projection).
- #43 M2a (Dashboard coding-loop start):
  - Server: `POST /loops/start` accepts `mode` / `from_loop` / `source_brief` (keep/drop) and `brief`. The guarded successor `init_loop(mode="coding")` is the only source validator (atomic); its errors are 400, and the single-active guard gives 409. `/loops` list entries gain the normalized `mode`.
  - UI: a Loop type radio and an approved-planning-loop picker filtered to planning `plan_approved` loops, with an empty state that disables Create. The source `/status` brief check runs behind revision and selection stale guards. The keep/drop checkbox shows for every non-absent state, with corrupt-state warning text and default keep, and is hidden for absent. The POST shape omits `sketch_path`, and the server's honest error is shown.
  - `dashboard.css`: create-form mode and source-brief styles.
- Tests:
  - `tests/test_dashboard_loop_brief.py` gains 19 coding-start tests: list mode; keep plus new brief; drop; none_available; 11 rejection cases each leaving no partial directory; an active loop gives 409; a corrupt source (mismatch, missing, invalid_ref) gives 400 under keep with the hint, and 201 under drop with nothing copied.
  - `tests/test_dashboard_ui/test_loop_brief_ui.py` gains 5 Playwright tests: mode toggle and filtering; no-source disabled; keep / drop / absent POST shapes; the corrupt warning, the honest error, then drop; a stale source response ignored. That last test holds the route without blocking the event loop, and was verified to fail only when both guards are removed.
- Charters: `scripts-dashboard.md` (coding start contract, list mode); `scripts-dashboard-ui.md` (coding creation UI).
- #46 M3 (plan context evidence):
  - `submit.py`: `context_checked_problems(text)` is a structural check of one `## Context Checked` section: fence-aware, comment-stripped, rejecting bare placeholders, accepting `None — <reason>`. `handle_submit_draft` reads the draft once. For `contract.context_evidence` sessions it validates the captured bytes in the lock (with a friendly preflight) and writes exactly those bytes; legacy sessions keep `_copy_artifact`.
  - Docs, each pair kept byte-identical:
    - Loop protocol: Step 2 covers the Architect brief as required reading, brief vs. sketch Context roles, reading charters first, and per-role bullets. Step 3 covers the Context Checked rules and the Reviewer's credible-context check. Rule 5, the coding two-brief / dropped rule, File Locations and the quick reference are updated.
    - `loop-artifact-formats.md`: the plan template gains `## Context Checked` with a `None — <reason>` example; the sketch Context comment now says background and points to the brief for must-read; the findings Scope Check gains the context prompt; the draftor guideline is added.
    - `/loop-join`: read the brief(s), the Context Checked requirement.
  - Tests:
    - Existing loop fixtures (`test_loop.py` and the three liveness suites) now submit contract-valid drafts. New planning sessions are flagged, which is the intended migration boundary.
    - New `tests/test_loop_context_evidence.py` (49 tests): validator units; flagged atomic reject and byte-exact accept; non-UTF-8; revision reject; in-lock authority; legacy accept; flag-shape strictness; coding has no contract; swap race in both directions; drift guards (pairs identical, the template passes, the protocol and `/loop-join` mention the brief and rules). Mutation-checked: a path copy in the lock fails the race test, and dropping the in-lock check fails 2 tests.
  - Charter: `scripts-loop.md` (`handle_submit_draft` contract, `context_checked_problems`, TRIPWIRE "Validated Bytes Are Persisted Bytes").
- #43/#46 M4 (review fix M4-1: the brief integrity wording now matches the contract, with POSIX-only read-only and status/carry-forward verification, and artifact viewing not described as verifying): the CHANGELOG `[Unreleased]` Added entries for the Architect brief (#43) and Context Checked (#46). The D4 follow-up is filed as #48: a shared INDEX parser that fixes #18, then an advisory charter-map warning on submit-draft.
- Pre-commit charter-index-gap fix: the `scripts-cross-cutting.md` Shipped-Copy Synchronization tripwire now records the `TestDriftGuards` pins: protocol, formats and `/loop-join` pair identity; the plan template passing the Context Checked validator; and the protocol and `/loop-join` naming the brief and rules.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
