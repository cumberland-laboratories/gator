---
message: "Loop: #37 Phase 1 — Codex routine participant profile (opt-in) and spike evidence"
change-type: docs
significance: medium
decision-tags: [loop, codex, execution-permission]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- cp1 (fixture, isolation and baseline): new evidence artifact `.gator/artifacts/2026-10-08-codex-routine-profile-spike.md`. It pins codex-cli 0.144.1 on Windows 10 19045 (elevated sandbox) and cites the Codex docs: `prefix_rule` `allow` runs the command outside the sandbox; `.git` is read-only inside every workspace-write writable root; `CODEX_HOME` is the only per-process config isolation, because rules are not profile-scoped. It also records the preflight manifest and `execpolicy check` baseline of the normal home, the disposable `%TEMP%` fixture, and the reproduced baseline: `git write-tree` / `submit-review --approve` → `.git/index.lock: Permission denied`, reported by Gator as `git_busy`, with the loop state unchanged.
- cp2 (profile happy path): artifact §7. A user-layer `prefix_rule(["gator","loop",[status|wait|submit-draft|submit-review|submit-implementation]], allow)` lives only in an isolated `CODEX_HOME`. Static match: 5/5 allow, 8/8 negatives no-match. Live `codex exec --ephemeral -s workspace-write` runs (Architect-approved substitute for the interactive session; auth.json copied with approval) gave:
  - the Codex Reviewer's approval advanced the fixture to `implementation_approved` with the live candidate check intact; a Codex Draftor ran submit-draft and submit-implementation;
  - direct `git write-tree` and `git add` stayed sandbox-denied, so the rule is command-scoped;
  - Gator's child Git runs unsandboxed, so this is a conditional pass that needs an Architect decision;
  - the PowerShell wrapper collapses Gator exit codes 2 and 3 to 1;
  - no token persisted in the spike home or the repo.
- cp3 (safety, rejection, teardown): artifact §8.
  - Under the profile: stale approval refused by Gator's freshness check; unrelated `git commit`, out-of-workspace write and uncovered `gator loop end` still sandboxed or role-rejected.
  - Profile removed: baseline denial with no state change and the token still valid; the model read Gator's `git_busy` as "lock contention", so the participant-text gap is confirmed.
  - Malformed rule: Codex refuses to start (fails closed). Terminal: the participant stops on "Loop ended."; the rule holds no loop data.
  - Teardown: spike home deleted (including the copied auth.json); no persistent environment variables; a fresh default-home session reproduces the baseline.
  - Finding: a default-home `codex exec` auto-added a fixture trust entry to `~/.codex/config.toml`. It was removed by a guarded script, and the file is byte-identical to preflight again.
- cp4 (packaging): the Architect chose "Publish as opt-in" on the escalated conditional pass (decision-1).
  - New `reference-notes/codex-routine-participant-profile.md` (`.includes` and starter, byte-identical). It leads with the trust cost (allowed `gator loop` commands and their Git children run outside the Codex sandbox) and covers dedicated-`CODEX_HOME` setup and removal, coverage, participant guidance (read text not exit codes; `git_busy` + Permission denied = host denial) and a validation checklist.
  - Links added in `codex-loop-participant.md` (Goal-mode note, now committed for the first time) and the Loop protocol runtime paragraph (both copies).
  - Both `gator_layout.py` copies add the two Codex notes to the reference-notes shipped fallback, per the `scripts-layout.md` tripwire, which now names them.
  - `test_starter_copies_match` covers `codex-loop-participant.md`. New `test_codex_routine_profile_copies_both_absent_or_identical` was checked failing on a one-sided copy, then passing.
