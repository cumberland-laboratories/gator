# Implementation: Codex Routine Loop-Command Profile Spike — Checkpoint 3 (Safety, rejection and teardown)

## Executive Summary

- **What changed:** evidence artifact §8 (stale candidate, unrelated commands, profile removed, malformed profile, terminal, teardown, post-teardown verification, matrix status) and the `commit_draft` entry. No code changed.
- **Key result:** the profile does not weaken Gator. A stale approval is refused by Gator's freshness check, and uncovered commands stay sandboxed or role-rejected. Removing the profile restores the baseline denial with no state change, and a malformed profile fails closed. The spike home is deleted, and the normal home is byte-identical to preflight.
- **Main risk / gap:** with the profile absent, the model read Gator's `git_busy` as "lock contention". The sketch's requirement that participant text identify execution permission is not met by current Gator output (Phase-1b candidate).
- **Incident handled:** a default-home `codex exec` auto-added a fixture trust entry to `~/.codex/config.toml`. A guarded script removed exactly that block, and the hash matches preflight again.

## Implementation Summary

- **§8.1 Stale candidate:** I staged a new tree after submission. The profiled Codex Reviewer's `--approve` got `Error: The candidate changed since submission … approval is blocked`. The state is identical before and after. The rule let the live snapshot run, and Gator's binding refused the approval.
- **§8.2 Unrelated commands under the profile:**
  - `git commit --allow-empty` → `index.lock` denied;
  - write to `C:\Users\curator\…` → `UnauthorizedAccessException`, no file;
  - `gator loop end` with the Reviewer token (not covered) → `Rejected: End requires the architect token`.

  HEAD and the loop state were unchanged.
- **§8.3 Profile removed:** with the rule file moved out of `rules\`, `--approve` gave the exact baseline `git_busy … index.lock … Permission denied`. The state is identical and the token is valid from an ordinary shell (`Your turn: YES`). The model's own diagnosis was "lock/permission contention", so the gap is recorded.
- **§8.4 Malformed rule:** both `execpolicy check` and `codex exec` stop with a starlark parse error. No session ran.
- **§8.5 Terminal:** the rule was restored and the loop ended by the Architect. The participant's bounded `wait` printed `Loop ended.` (exit shown as 1 via the wrapper), and it said it would stop. The rule file contains no token, loop id or path.
- **§8.6–8.7 Teardown and verification:**
  - spike home deleted, including the copied `auth.json` and the sandbox-user credentials;
  - no persistent `CODEX_HOME` / `GIT_CONFIG_*` / `CODEX_SQLITE_HOME`;
  - fixture absent from global `safe.directory`;
  - normal-home manifest identical, and `execpolicy check` from the normal home gives 10/10 `no-match`;
  - a fresh default-home Codex session on a new candidate reproduced the baseline denial with no state change.
- **§8.8 Incident:** that default-home run was Codex's first run in the fixture without the pre-trusting spike home, and Codex appended `[projects.'…\gator-codex-spike-20261008\repo'] trust_level = "trusted"` to the normal config. I removed it with `work\restore_config.py`, which writes only when the result hashes to the preflight value; the result is `eeabec50…`, byte-identical. Packaging lesson: a dedicated `CODEX_HOME` must pre-trust the repository.
- **§8.9 Matrix:** four rows pass. One gap is recorded on the denial-text row.

## Charter Updates

None. No chartered code changed. §8.1 relies on the Loop charter's `handle_submit_review` rule ("APPROVE is rejected unless the live staged tree AND HEAD still equal the submitted candidate"). The observed message matches that path. §8.3 and §8.5 match the `snapshot()` `git_busy` code and the status/wait terminal behavior.

## Verification

- Every probe records fixture state before and after via `work\loopstate.py` (stage, generations, events, index SHA, object count, `index.lock`), plus parsed `codex exec --json` command items (logs in `work\sessionC1–C5.jsonl` and `sessionD.jsonl`, outside the repository).
- Teardown checks were run directly:
  - `[Environment]::GetEnvironmentVariable` at User and Machine scope for six variable names;
  - `Get-FileHash` of `config.toml` and `rules\default.rules`;
  - `codex execpolicy check` on the 10 preflight commands;
  - `git config --global --get-all safe.directory`;
  - checking the spike-home path no longer exists.
- The config restore was guarded. The script printed `occurrences 1`, `candidate sha eeabec50…`, `restored`, and an independent `Get-FileHash` then returned `eeabec50…`.
- **Known gaps:**
  - The interactive TUI was still not observed.
  - The participant-text gap needs a Gator change (out of scope).
  - The fixture directory remains until checkpoint 4 is approved, then it is deleted.
  - Fixture loops are terminal: two `ended_by_architect` and one `implementation_approved` (`PENDING COMMIT`, blocked by the fixture's own charter gate, which is irrelevant to the spike).

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp3 (3 of 4) — Safety, rejection and teardown |
| Checkpoint base tree | `a13ee972048798b0065647d2c8e8b9042bdbe016` |
| Generation | 2 |
| Staged tree (candidate) | `4694815498825fe3cdb261da492e077ef4089b63` |
| Changed paths in this checkpoint | 2 (M 2) |
| Loop base HEAD | `660480758c2d6a1b41157109f9f5625b3c89cc33` |
| Loop base tree | `101a914d85b07ffd2a1c8fbc6c40748f5862cda8` |
| Current HEAD | `660480758c2d6a1b41157109f9f5625b3c89cc33` (dev) |
| Changed paths vs loop base (cumulative) | 3 |
| Unstaged / untracked residue | 5 other + 31 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff a13ee972048798b0065647d2c8e8b9042bdbe016 4694815498825fe3cdb261da492e077ef4089b63
```

Cumulative context (approved checkpoints plus this one): `git diff 101a914d85b07ffd2a1c8fbc6c40748f5862cda8 4694815498825fe3cdb261da492e077ef4089b63`.

Changed paths in this checkpoint (status, path):

```text
M .gator/artifacts/2026-10-08-codex-routine-profile-spike.md  [revisits an earlier checkpoint]
M .gator/commit_draft.md  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.includes/procedures/gator-loop-protocol.md
.gator/.includes/reference-notes/codex-loop-participant.md
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md
src/gator_command/templates/gator-starter/reference-notes/codex-loop-participant.md
```

Loop residue: 31 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
