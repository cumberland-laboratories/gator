# Implementation: Codex Routine Loop-Command Profile Spike — Checkpoint 1 (Fixture, isolation and baseline evidence)

## Executive Summary

- **What changed:** a new evidence artifact, `.gator/artifacts/2026-10-08-codex-routine-profile-spike.md`, with sections 1–6 (environment, cited Codex docs, isolation verdict, normal-home preflight, fixture, baseline), plus the `commit_draft` entry. No code changed.
- **Key decision:** isolation uses a process-scoped `CODEX_HOME`. Rules are per config layer and not profile-scoped, so `--profile` cannot carry a rule. A pass would therefore package a dedicated `CODEX_HOME` as the opt-in unit.
- **Main finding:** H1 is confirmed. Under the Codex workspace-write sandbox, `git write-tree` cannot create `.git/index.lock`, and `submit-review --approve` fails. Gator labels the failure `git_busy`. The loop state is unchanged.
- **Verified:** before/after stage, generation, event, index and object counts are identical. The fixture lives only in `%TEMP%`. The normal home was not written.

## Implementation Summary

This checkpoint delivers the evidence base the later checkpoints build on. It adds no product behavior.

- **Environment (§1):** `codex-cli 0.144.1`, Windows 10 Home 19045, `[windows] sandbox = "elevated"`, `gator 2.23.0`, Git 2.40.0.
- **Documentation (§2):** the Codex docs, retrieved 2026-10-07 (`developers.openai.com` now redirects to `learn.chatgpt.com`), with verbatim quotes where they bear on the plan:
  - the `allow` decision "Run[s] the command outside the sandbox without prompting";
  - the protected-paths list (`.git` is read-only in every writable root);
  - `CODEX_HOME` sets the root for config, auth and rules;
  - rules load per config layer, including trusted project `.codex/rules/`.

  Documentation gaps that checkpoint 2 must observe: child-process inheritance, and how PowerShell wrapping is matched.
- **Isolation verdict (§3):**
  - (a) `CODEX_HOME` exists as a per-process selector;
  - (b) rules load from each config layer's `rules/`;
  - (c) `--profile` and `-c` cannot scope rules.

  Feasible, with the stated packaging consequence.
- **Preflight (§4):**
  - SHA-256 of `~\.codex\config.toml` and `~\.codex\rules\default.rules`; there are no profiles, and the credential file is not hashed.
  - `execpolicy check` from the normal home: `no-match` for all 10 probe commands (5 positive loop commands, `gator loop end`, `git write-tree`, `git commit`, `git update-ref`, and the PowerShell-wrapped approval).
  - Observation for the Architect: the normal `default.rules` already contains broad remembered allows (`git add`, `git commit -m`, `gator gatorize`, `rg`, …), and these run unsandboxed. The spike does not touch them.
- **Fixture (§5):** `%TEMP%\gator-codex-spike-20261008\`. The repo was gatorized and committed through the real strict commit gate. A planning loop was approved through the CLI, and a one-checkpoint coding loop was submitted by the draftor from an ordinary shell. The candidate tree is `2049d8ba…` and the stage is `implementation_review`. Tokens are kept only in `work\tokens.env`, outside every repository.
- **Baseline (§6):** `codex sandbox -c sandbox_mode="workspace-write"`, which is the elevated sandbox without a model. Two confounds were found and controlled without global changes:
  - the sandbox runs as a separate user, so Git rejects the fixture on ownership grounds. This was mirrored per process with `GIT_CONFIG_COUNT`/`KEY_0`/`VALUE_0=safe.directory`, matching how the Architect's real repos are listed in `~/.gitconfig`;
  - the sandbox runner cannot launch a bare `gator`. Probes used the `powershell.exe -Command "gator …"` shape that interactive Codex uses.

  Results:

  | Probe | Result |
  |---|---|
  | read-only tree diff | ok |
  | `git diff --name-only` | ok |
  | Reviewer `status` | ok |
  | `git write-tree` | **index.lock Permission denied** |
  | `submit-review --approve` | **`Error: Cannot verify the live candidate before approval: git_busy (fatal: Unable to create '…/.git/index.lock': Permission denied)`** |

- **Q4 observation (§6.4):** Gator's `git_busy` label hides the permission cause. A Phase-1b candidate (distinct error code) is recorded. It is not implemented, because snapshot changes are a sketch non-goal.

## Charter Updates

None. No code under a chartered path changed. The artifact cites `.gator/charters/scripts-loop.md` (`snapshot()` error codes, `handle_submit_review`). I re-checked the `git_busy` definition ("an index-lock failure persists after one retry") and `_is_busy` / `_BUSY_MARKERS` in `src/gator_command/scripts/loop/gitsnap.py` against the observed output. The charter matches the code, so no drift was found.

## Verification

- **Loop state (§6.3):** recorded by `work\loopstate.py` before the probes, after P0 and after P2. All three lines are identical: `stage=implementation_review generations=1 events=2 last_event=implementation_submitted approval=no index_sha=e96ec14b71913a03 objects=106 index_lock=False`.
- **Fixture location:** every fixture path is under `%TEMP%\gator-codex-spike-20261008\`. `git diff --cached --stat` in this repository shows only the evidence artifact, `.gator/commit_draft.md` and one session snippet that was already staged (expected residue under the constitution).
- **Normal home:** not written. No `CODEX_HOME` and no Git config were set beyond the probe process. `git config --global --get-all safe.directory` is unchanged; the fixture is not listed.
- **Known gaps, deferred as planned:**
  - The interactive Goal-mode baseline (prompt vs deny presentation in the TUI) is exercised in checkpoint 2's fresh-session run. Checkpoint 1 uses the model-free sandbox runner, which applies the same sandbox.
  - Two background `gator loop start` host processes for the fixture loops ran from this session. The planning host exited at `plan_approved`, and the coding host is still running for checkpoint 2.
- **Cross-Cutting charter:** not re-read for this checkpoint, which touches no code. It will be read before checkpoint 4 changes tests.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp1 (1 of 4) — Fixture, isolation and baseline evidence |
| Checkpoint base tree | `101a914d85b07ffd2a1c8fbc6c40748f5862cda8` |
| Generation | 0 |
| Staged tree (candidate) | `9cc960dffbe6dcdba87ace4d1e674716b65a66b6` |
| Changed paths in this checkpoint | 3 (A 2, M 1) |
| Loop base HEAD | `660480758c2d6a1b41157109f9f5625b3c89cc33` |
| Loop base tree | `101a914d85b07ffd2a1c8fbc6c40748f5862cda8` |
| Current HEAD | `660480758c2d6a1b41157109f9f5625b3c89cc33` (dev) |
| Changed paths vs loop base (cumulative) | 3 |
| Unstaged / untracked residue | 5 other + 25 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 101a914d85b07ffd2a1c8fbc6c40748f5862cda8 9cc960dffbe6dcdba87ace4d1e674716b65a66b6
```

Cumulative context (approved checkpoints plus this one): `git diff 101a914d85b07ffd2a1c8fbc6c40748f5862cda8 9cc960dffbe6dcdba87ace4d1e674716b65a66b6`.

Changed paths in this checkpoint (status, path):

```text
A .gator/artifacts/2026-10-08-codex-routine-profile-spike.md
M .gator/commit_draft.md
A .gator/session-snippets/2026-10-07-gator-660480758c2d6.json
```

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.includes/procedures/gator-loop-protocol.md
.gator/.includes/reference-notes/codex-loop-participant.md
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
src/gator_command/templates/gator-starter/procedures/gator-loop-protocol.md
src/gator_command/templates/gator-starter/reference-notes/codex-loop-participant.md
```

Loop residue: 25 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
