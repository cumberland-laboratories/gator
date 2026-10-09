# Implementation: Codex Routine Loop-Command Profile Spike — Checkpoint 2 (Profile happy path)

## Executive Summary

- **What changed:** evidence artifact §7 and the `commit_draft` entry. It covers the mechanism, the static match table, live Reviewer and Draftor runs, the required per-mechanism evidence row, additional findings and the checkpoint verdict. No code changed.
- **Key result:** a user-layer `prefix_rule` for the five `gator loop` subcommands, in an isolated `CODEX_HOME`, lets a Codex Reviewer's `submit-review --approve` advance the fixture with Gator's live candidate check intact. Direct `git write-tree` and `git add` stay sandbox-denied.
- **Main risk / decision:** `allow` runs the matched `gator` and its child Git **outside the sandbox**. That makes this a conditional pass, which the plan says needs an Architect decision before checkpoint 4 packages anything.
- **Deviation (Architect-approved 2026-10-07):** non-interactive `codex exec --ephemeral` replaced the interactive TUI session, and `auth.json` was copied instead of running `codex login`. The interactive prompt display was not observed.

## Implementation Summary

- **Mechanism (§7.1):**
  - `<scratchpad>\spike-codex-home\rules\default.rules` contains one `prefix_rule(pattern=["gator","loop",[status, wait, submit-draft, submit-review, submit-implementation]], decision="allow")` with inline `match`/`not_match` examples. It is byte-identical after all runs (SHA-256 `eaacd4d1…`).
  - The spike `config.toml` holds only model, elevated Windows sandbox and fixture trust.
  - `CODEX_HOME` and `GIT_CONFIG_PARAMETERS` (`safe.directory` for the fixture) are set at process scope only.
  - A fresh home re-ran Codex's sandbox setup and wrote sandbox-user credentials into the spike home; teardown deletes them (cp3).
- **Static match (§7.2):** `codex execpolicy check` gives `allow` for 5/5 subcommands and `no-match` for `gator loop end`, `extend`, `gator gatorize`, `git write-tree`, `git commit`, `git update-ref`, and both PowerShell-wrapped forms. Q5 answer: a literal prefix rule is enough. The live session unwrapped simple `powershell.exe -Command` invocations, and a dynamic trailing token does not affect the prefix match.
- **Live runs (§7.3):**
  - Session A (Reviewer): `status`, `wait`, `git write-tree` **denied** (index.lock), `submit-review --approve` **succeeded**. The fixture moved `implementation_review → implementation_approved`, and the Reviewed Candidate shows `Live candidate unchanged at review: yes`.
  - Session B (Draftor): `submit-draft` ok, `wait` ok, `git add` **denied** (index.lock), `submit-implementation` **succeeded** (runs `write-tree`).
- **Evidence row (§7.4):** all four columns are filled with observed facts:
  - match decisions;
  - no approval request across 10 covered invocations in fresh, ephemeral sessions (interactive display not observed);
  - matched command unsandboxed but session sandbox not widened (P-write);
  - child Git inherits the unsandboxed context (P-child).
- **Additional findings (§7.5):**
  - Windows PowerShell 5.1's `-Command` wrapper collapses Gator exit codes 2 and 3 to 1 (reproduced directly), which breaks exit-code-keyed bounded waiting for Codex participants;
  - the model once mis-copied a token, and Gator failed closed;
  - an `rg -uu -a` scan found no token in the spike home or in this repo;
  - the normal-home manifest is unchanged.

## Charter Updates

None. No chartered code changed. The P-child inference relies on the Loop charter's `handle_submit_review` coding-path contract: APPROVE is rejected unless the live staged tree and HEAD equal the candidate, and a failed live snapshot yields "Cannot verify…". The §6.2 baseline output confirms that path against the code.

## Verification

- **Fixture state:** PRE-A / POST-A lines are in §7.3: stage `implementation_review` → `implementation_approved`, `approval=no` → `yes`, events 3 → 4, index bytes and object count unchanged, no stale `index.lock`.
- **Codex event logs:** `codex exec --json` logs (`work\sessionA.jsonl`, `sessionB1.jsonl`, `sessionB2.jsonl`, outside the repository) were parsed for every `command_execution` item: command, exit code, last output lines. They are quoted in §7.3 with tokens redacted.
- **Exit-code collapse:** reproduced outside Codex: direct `wait` → 2; `powershell.exe -Command "gator loop wait …"` → 1; with `; exit $LASTEXITCODE` → 2.
- **Token persistence:** `rg -uu -l -a` for every fixture token over the spike home and this repository (excluding `.gator/loops/` and `.git/`) found no hits.
- **Normal home:** `config.toml` `eeabec50…` and `default.rules` `3a1f0627…` are unchanged from preflight.
- **Known gaps:**
  - The interactive TUI approval display was not observed.
  - Whether the `; exit $LASTEXITCODE` form escapes the allow rule was not tested live.
  - Whether Codex's environment filter drops `GIT_CONFIG_KEY_0` was not tested.
- **Fixture left for checkpoint 3:**
  - coding loop `add-multiply-coding-…` in `implementation_review`, with an unstaged `mul` edit available to create a stale candidate;
  - the copied `auth.json` and the spike home remain until teardown.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 4) — Profile happy path |
| Checkpoint base tree | `9cc960dffbe6dcdba87ace4d1e674716b65a66b6` |
| Generation | 1 |
| Staged tree (candidate) | `a13ee972048798b0065647d2c8e8b9042bdbe016` |
| Changed paths in this checkpoint | 2 (M 2) |
| Loop base HEAD | `660480758c2d6a1b41157109f9f5625b3c89cc33` |
| Loop base tree | `101a914d85b07ffd2a1c8fbc6c40748f5862cda8` |
| Current HEAD | `660480758c2d6a1b41157109f9f5625b3c89cc33` (dev) |
| Changed paths vs loop base (cumulative) | 3 |
| Unstaged / untracked residue | 5 other + 29 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 9cc960dffbe6dcdba87ace4d1e674716b65a66b6 a13ee972048798b0065647d2c8e8b9042bdbe016
```

Cumulative context (approved checkpoints plus this one): `git diff 101a914d85b07ffd2a1c8fbc6c40748f5862cda8 a13ee972048798b0065647d2c8e8b9042bdbe016`.

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

Loop residue: 29 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
