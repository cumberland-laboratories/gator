# Implementation: Codex Loop Profile Launcher, Checkpoint 2 (Verified Launch and Command Surface)

## Executive Summary

- **What changed:** `codex_launcher.py` gains the per-launch `codex execpolicy` boundary proof, Codex resolution and the version warning, Windows-only refusal, the trust-cost and first-sign-in output, and the child-only `CODEX_HOME` launch that returns Codex's exit code. `gator loop codex [--dry-run] [--home]` is wired in `loop/cli.py`. Both copies of the reference note gain "Quick Setup: `gator loop codex`".
- **Key decision:** every refusal before preparation writes nothing (not governed, non-Windows, bad home, conflicts, Codex missing). A failed boundary proof blocks the launch. The CLI has no token argument, and the probes use only literal placeholders.
- **Real-Codex evidence:** the integration test runs the installed `codex execpolicy` (0.144.1) against `RULE_BYTES` and passes. A manual `gator loop codex --dry-run` in this repo printed the plan and created nothing under `~/.gator/adapters`.
- **Verification:** the focused suites pass (505 tests, no skips). The final broad suite `python -m pytest tests -q` gives **2492 passed, 22 skipped, 2 xfailed** (20m09s).

## Implementation Summary

- **`src/gator_command/scripts/loop/codex_launcher.py`** (additions only; the checkpoint 1 code is unchanged):
  - Constants: `TRUST_WARNING` (the sketch's trust cost: allowed commands and their children run outside the sandbox with the user's rights; everything else stays under normal policy; Gator still enforces token/role/turn/freshness), `SIGN_IN_NOTE` (the sketch's two lines) and `POLICY_PROBES` (`gator loop status --token x` → allow; `git write-tree` and `gator loop end --token x` → no match).
  - `child_env(env, home)` returns a copy with `CODEX_HOME`.
  - `codex_version(codex, run)` parses `x.y.z`; None on failure.
  - `check_policy(codex, rules_path, env, run)` runs `[codex, "execpolicy", "check", "--rules", <rules>, "--", *argv]` for each probe with the dedicated `CODEX_HOME`. It raises `ProfileError` on an OS error, a non-zero exit, non-JSON output, or a decision or match that differs from the expected one.
  - `launch(codex, repo_root, env, run)` runs `run([codex], cwd=str(repo_root), env=env).returncode`: an argument list, no shell.
  - `main(args, *, env, platform, which, run, cwd, tempdir)`, in order: `find_gator_root(cwd)` → Windows check → `validate_home` → `plan_preparation` → `--dry-run` prints `render_dry_run` and returns 0 → `which("codex")` → version warning → `apply_preparation` → `check_policy` → summary (home, trusted key, verified boundary), `TRUST_WARNING`, `SIGN_IN_NOTE` if `auth.json` is absent, and the "Next: `gator loop join` … `/goal`" line → `launch`.
    - A non-zero exit without `auth.json` prints the recovery hint naming the resolved `CODEX_HOME` and `codex login`.
    - Any `ProfileError` prints the message (with the manual-note pointer) to stderr and returns 1.
- **`src/gator_command/scripts/loop/cli.py`:** a `codex` subparser (`--dry-run`, `--home`; help points to the note). `_cmd_codex` lazily imports `codex_launcher.main` and calls `sys.exit` with its result. The dispatch table gains `"codex"`; no other subcommand changed.
- **`reference-notes/codex-routine-participant-profile.md`** (template and dogfood, byte-identical): a new "Quick Setup: `gator loop codex`" section before Setup. It covers:
  - the four per-run steps (home and refusals, rule plus owned config block, rule check, trust cost and child-only launch);
  - first sign-in, with no credential copying;
  - the join → `/goal` flow;
  - `--dry-run`;
  - "never starts, joins, or authorizes a loop; never takes a token";
  - the stop-without-changes cases with the fallback to manual Setup;
  - Windows-only use and the version warning;
  - removal.
  
  The manual Setup is unchanged.

## Charter Updates

- **`scripts-loop.md`:**
  - New entries `codex_version / check_policy / child_env / launch` (probes, raise conditions, placeholder-only arguments, child-only env) and `main(...)`: the ordered flow; refusals write nothing; `auth.json` existence-only; injected seams are test-only.
  - Owns: `cli.py` now routes **17** subcommands, including `codex [--dry-run, --home]`.
  - The `main(argv)` entry lists `codex` and notes the lazy import and the absence of a token argument.
- **`scripts-cross-cutting.md`:** Shipped-Copy Synchronization records that `tests/test_loop_codex_launcher.py` pins the note pair's byte-identity and `RULE_TEXT` ↔ the note's rule.
- **Checks against the code:** every function and constant named in the new entries exists (grep); the `main` order in the charter matches the code line by line; the dispatch table and subparser show 17 subcommands.
- **`commit_draft.md`:** a checkpoint 2 bullet is appended and staged.

## Verification

- `python -m pytest tests/test_loop_codex_launcher.py tests/test_loop.py tests/test_packaging.py tests/test_native_file_guidance.py tests/test_loop_attention.py tests/test_loop_context_evidence.py -q -rs`: **505 passed, 0 skipped**.
- New tests in `tests/test_loop_codex_launcher.py` (40 total in the file). They use a `FakeRun` that answers `--version`, `execpolicy check` in the real JSON format, and the launch:
  - `test_launch_passes_codex_home_to_child_only`:
    - the launch argv is exactly `[codex_path]`, with `cwd=repo`, `env["CODEX_HOME"]` set to the resolved home and no `shell` keyword;
    - all three probes carry the same `CODEX_HOME`;
    - `os.environ` is unchanged and `main` returns the child's code (7);
    - the trust cost and sign-in note are printed, with no version warning on 0.144.1.
  - `test_launch_policy_gate_blocks_launch`: five parameterized cases (status not allowed, write-tree matched, loop-end matched, non-zero exit, non-JSON). Each returns 1, makes no launch call and prints the manual-note pointer.
  - `test_launch_refusals_are_non_destructive`: Codex missing, non-Windows and not governed. Each returns 1, makes no subprocess call, and the home does not exist.
  - `test_launch_warns_on_unverified_version` (0.150.0 → warning, still launches) and `test_launch_recovery_hint_when_sign_in_did_not_complete` (exit 2 → hint with the resolved home and `codex login`).
  - `test_launch_skips_sign_in_note_when_home_has_login`: `Path.read_text`/`read_bytes` are guarded to fail if `auth.json` is ever read.
  - `test_launch_dry_run_via_cli_routing_writes_nothing` (through `loop.cli.main([...])`) and `test_launch_cli_has_no_token_argument` (help text).
  - `test_launch_real_codex_execpolicy_proves_boundary`: **ran (not skipped)** against the installed Codex 0.144.1.
  - `test_launch_reference_note_documents_quick_setup` [template, dogfood] and `test_launch_reference_note_pair_is_byte_identical`.
- **Manual:** `python src/gator_command/scripts/gator-loop.py codex --dry-run` in this repo printed the home `C:\Users\curator\.gator\adapters\codex\loop-home`, the key `[projects.'c:\users\curator\code2\gator']`, the four planned actions and the rule. `~/.gator/adapters` does not exist afterwards.
- **Final broad suite:** `python -m pytest tests -q -p no:cacheprovider` gives **2492 passed, 22 skipped, 2 xfailed in 1209.93s**.
- **Not done:** no interactive Codex session was launched (the plan's tests never launch a real TUI). The first real `gator loop codex` run, including sign-in, is left to the Architect.
- **Unstaged:** `.gator/.gator-version` and `.gator/runtime-pin.json` (the earlier pin advance) stay unstaged. The previous session snippet stays staged as residue.

## Commit State

<!-- Captured by the gator loop CLI at submission. Authoritative:
     author text in this section is replaced. The reviewed candidate
     is the staged tree below, not this artifact's prose. -->

| Fact | Value |
|---|---|
| Checkpoint | cp2 (2 of 2) — Verified launch and command surface |
| Checkpoint base tree | `92acce6d70fbb116e197bd8d2792ab64a1b7d6aa` |
| Generation | 1 |
| Staged tree (candidate) | `7e01b49b16a02cb832fd21eda069d58736482b40` |
| Changed paths in this checkpoint | 8 (M 8) |
| Loop base HEAD | `7140baf048b0f667ceb1e24fb3ec0b01c9cb78db` |
| Loop base tree | `aa7d41181d91c6252b79abacd0da94e835d10de7` |
| Current HEAD | `7140baf048b0f667ceb1e24fb3ec0b01c9cb78db` (dev) |
| Changed paths vs loop base (cumulative) | 10 |
| Unstaged / untracked residue | 3 other + 75 loop residue under `.gator/loops/` (none of it is part of the candidate) |

Review exactly this checkpoint with:

```text
git diff 92acce6d70fbb116e197bd8d2792ab64a1b7d6aa 7e01b49b16a02cb832fd21eda069d58736482b40
```

Cumulative context (approved checkpoints plus this one): `git diff aa7d41181d91c6252b79abacd0da94e835d10de7 7e01b49b16a02cb832fd21eda069d58736482b40`.

Changed paths in this checkpoint (status, path):

```text
M .gator/.includes/reference-notes/codex-routine-participant-profile.md
M .gator/charters/scripts-cross-cutting.md  [revisits an earlier checkpoint]
M .gator/charters/scripts-loop.md  [revisits an earlier checkpoint]
M .gator/commit_draft.md  [revisits an earlier checkpoint]
M src/gator_command/scripts/loop/cli.py
M src/gator_command/scripts/loop/codex_launcher.py  [revisits an earlier checkpoint]
M src/gator_command/templates/gator-starter/reference-notes/codex-routine-participant-profile.md
M tests/test_loop_codex_launcher.py  [revisits an earlier checkpoint]
```

Paths marked as revisiting an earlier checkpoint were also changed by an approved checkpoint; this is information for the Reviewer, not a prohibition.

Unstaged / untracked residue (disclosed; NOT part of the candidate):

```text
.gator/.gator-version
.gator/runtime-pin.json
.gator/session-snippets/2026-10-06-gator-2d6996c33c4b8.json
```

Loop residue: 75 path(s) under `.gator/loops/` (this loop's own audit files; expected, not part of the candidate).
