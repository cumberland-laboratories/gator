# Implementation Plan: One-Command Codex Loop Profile Launcher (#37 follow-up)

## Executive Summary

- **Proposal:** add `gator loop codex [--dry-run] [--home PATH]`.
  - It prepares a dedicated, loop-only `CODEX_HOME` (default `~/.gator/adapters/codex/loop-home/`) holding exactly the verified five-subcommand rule and a Gator-owned trust/sandbox block for the current governed repository.
  - It proves the rule boundary with `codex execpolicy check`, prints the trust cost, and launches interactive `codex` with `CODEX_HOME` set for the child process only.
- **Key decision:** Python ≥3.9 has no TOML writer, so Gator owns a single marker-delimited block at the end of the dedicated home's `config.toml` and never edits user content outside it. Conflicting user tables, unfamiliar rule files and edited rules fail closed with a pointer to the manual profile note.
- **Main risk:** this crosses the loop charter's "Does Not Own: auto-launching of agent sessions" line. The sketch authorizes the explicit, opt-in launcher, and the charter boundary is narrowed to say exactly that (it never starts, joins or authorizes a loop).
- **Verification:** two responsibility checkpoints. Unit tests use injected runners, plus one real `codex execpolicy` integration test that is skipped when Codex is absent.

## Summary

The plan packages the #37 Phase 1 profile as one opt-in command, as the sketch describes.
- **Preparation** is idempotent, plan-then-apply, and fully previewable with `--dry-run`. It writes only inside the dedicated home.
- **The launch** verifies the policy boundary on every run and launches Codex with a process-local `CODEX_HOME`. It returns Codex's exit status and handles no tokens.
- **Unchanged:** the rule text, the allow-list, `gator loop join`, Goal mode and every other Gator behavior.

## Context Checked

- No Architect brief: `gator loop status` lists none for this loop.
- `sketch.md` (this loop).
- Protocol and formats: `.gator/.includes/procedures/gator-loop-protocol.md`, `.gator/.includes/reference-notes/loop-artifact-formats.md`, `.gator/procedures/writing-implementation-plans.md`.
- Charters:
  - `.gator/charters/INDEX.md` (`scripts/loop/**` → loop charter).
  - `scripts-loop.md`: Owns (`cli.py` owns 16 subcommands), **Does Not Own: "Auto-launching of agent sessions"**, `main(argv)`, Before Changing.
  - `scripts-cross-cutting.md`: Package and License Surface (explicit `package-data` for new `scripts/loop/*` modules, guarded by `tests/test_packaging.py`), Import Boundaries, CLI JSON schema rule.
- Code:
  - `src/gator_command/scripts/loop/cli.py`: `main()` subparser registration and the dispatch table, lines ~1626–1828.
  - `src/gator_command/scripts/gator-loop.py`: the thin entry.
  - `src/gator_command/scripts/gator_core.py`: `~/.gator/...` constants (`PREFERENCES_FILE`, `DASHBOARD_REGISTRY`, `machine-id`) and `find_gator_root`.
  - `pyproject.toml`: `requires-python = ">=3.9"`, the explicit `scripts/loop/*.py` package-data list, and no TOML dependency.
- Prior artifacts:
  - `.gator/.includes/reference-notes/codex-routine-participant-profile.md`: the exact rule, the config shape, the BOM warning, the TEMP-directory refusal, the checklist and removal.
  - `.gator/artifacts/2026-10-08-codex-routine-profile-spike.md`:
    - §7.1: home contents and side effects;
    - §7.2: match results;
    - §8.8: Codex itself writes trust keys as `[projects.'c:\users\…\repo']`, lowercase, and a dedicated home must pre-trust the repo.
- **Local probes:**
  - `shutil.which("codex")` resolves to `…\AppData\Roaming\npm\codex.CMD`, and `codex --version` prints `codex-cli 0.144.1`.
  - `codex execpolicy check --rules <rule> -- gator loop status --token x` prints `{"matchedRules":[…],"decision":"allow"}`.
  - The same check for `git write-tree` and `gator loop end --token x` prints `{"matchedRules":[]}`.

## Approach

**Planning path:** a full planning loop (as started by the Architect). Two responsibilities: a new public CLI subcommand and a machine-local trust boundary.

**Module map:**

| Module | Responsibility (one sentence) | Invariant owned |
|---|---|---|
| `scripts/loop/codex_launcher.py` (new) | Prepare, verify and launch the dedicated Codex loop profile. | Writes only inside the dedicated home; never reads the normal Codex home; never handles tokens; `CODEX_HOME` only in the child's environment. |
| `scripts/loop/cli.py` (existing seam) | Route `gator loop codex` and its two flags to the launcher. | No other subcommand changes. |

**Key design decisions:**

1. **Placement.** The launcher lives in the loop package, so `gator loop codex` keeps the `gator loop` namespace the sketch asks for. It is still a separate module with no imports from `session` / `state_machine` / `submit` / `host`, so it cannot affect loop authority.
2. **Dedicated home.**
   - The default is `Path.home()/".gator"/"adapters"/"codex"/"loop-home"`. `--home` overrides it.
   - Validation refuses, before any write, a home that:
     - is the normal Codex home (`~/.codex` or the caller's `CODEX_HOME` env value);
     - is inside the governed repository;
     - is under the system temp directory (Codex refuses its helpers there, per the reference note).
   - All of these comparisons use resolved, case-folded paths on Windows.
3. **Rule ownership.** The rule file is `rules/default.rules`, the file name the spike verified. Its content is the exact rule from the reference note, encoded as UTF-8 without a BOM with LF line endings, held as one module constant `RULE_TEXT`.
   - **Absent:** write it.
   - **Byte-equal to `RULE_TEXT`** (or to an entry in `KNOWN_GENERATED_RULES`, the same text with CRLF endings): leave it, or normalize it to the current form.
   - **Anything else:** fail closed with "unfamiliar rule; see the manual profile note".
   - **Any other file in `rules/`:** fail closed, because Codex may load it and widen the allow-list.
4. **Config ownership without a TOML library.** Gator owns exactly one block, always kept at the **end** of `config.toml`:

   ```toml
   # BEGIN GATOR LOOP PROFILE — managed by `gator loop codex`; edit outside this block only
   [windows]
   sandbox = "elevated"

   [projects.'c:\users\me\code\repo']
   trust_level = "trusted"
   # END GATOR LOOP PROFILE
   ```

   - **Regeneration:** remove the old block, keep every other byte, then append the new block. Its trusted-project set is the union of the keys already in our block (parsed only from our own generated line format) and the current repo.
   - **Why at the end:** a table header at the end cannot capture user top-level keys.
   - **`[windows]`** is emitted only on Windows.
   - **Fail-closed conflicts:** a line-level scan of the text outside our block that finds `[windows]` (on Windows) or a `[projects…]` header containing the same trust key makes Gator stop instead of creating a duplicate table, which would make Codex refuse to start.
   - **Malformed block:** begin without end, duplicated markers, or a `'` in a repo path (which literal-quoted TOML keys cannot hold) also fail closed.
   - **Optional parse check:** on Python ≥3.11, `tomllib` parses the rendered result before any write; a parse error fails closed. On 3.9/3.10 the closed generator plus the scan is the guard.
   - **Encoding:** written UTF-8 without a BOM, preserving the file's existing line endings.
5. **Trust key.** On Windows it uses the form Codex itself writes (§8.8): `str(repo_root.resolve())` with backslashes, lowercased, without a `\\?\` prefix. On other platforms it uses the resolved POSIX path. The key is printed in the preparation summary and in `--dry-run`, which satisfies "after showing it to the user".
6. **Plan/apply separation.** `plan_preparation()` is read-only and returns the ordered actions. `--dry-run` prints them, along with the resolved home, the rule, the trust entry and the launch argv, and exits 0. `apply_preparation()` executes only the planned actions.
7. **Verification on every launch.** Three `codex execpolicy check --rules <home>/rules/default.rules -- …` runs:
   - `gator loop status --token x` must parse as JSON with `"decision": "allow"`;
   - `git write-tree` and `gator loop end --token x` must report `matchedRules == []`.
   
   Any other result, a non-zero exit or unparseable output stops before launch. These children also get `CODEX_HOME=<dedicated home>`, so they cannot touch the normal home.
8. **Supported surface.**
   - **Platform:** Windows is supported, because it is the only verified OS. Any other OS fails with a pointer to the manual note's validation checklist.
   - **Codex version:** the launcher reads `codex --version`. A version other than `0.144.1` prints an "unverified Codex version" warning but continues, because the boundary is re-proved by `execpolicy` on every launch.
   - **Missing Codex:** `shutil.which("codex")` returning None fails with the manual-note pointer.
9. **Launch.**
   - It prints the trust warning (the sketch's text: allowed Gator Loop commands and their children run outside the sandbox with the user's rights; everything else stays under normal Codex policy).
   - If `<home>/auth.json` does not exist (existence check only, never read), it prints the two-line first-sign-in note.
   - It runs `subprocess.run([codex_path], cwd=repo_root, env={**os.environ, "CODEX_HOME": str(home)})` with an argument list and no shell. The parent's `os.environ` is never mutated, and the process exits with Codex's return code.
   - If Codex exits non-zero and `auth.json` is still absent, it prints the recovery hint: the resolved `CODEX_HOME` and `codex login` run with that home.
10. **No token surface and no state removal command.** No token flag exists. Removal is documented as deleting the dedicated home directory (the sketch allows "documented directory removal"). The launcher prints the home path in every run.

**Simplicity boundary:**
- No shared configuration framework, no TOML library and no generic adapter registry.
- No `--yes`, profile name, command list or config-merge flag.
- No Goal-mode automation and no changes to the protocol, `/loop-join` or the Dashboard.

**Rejected alternatives:**
- **Full TOML round-trip editing:** this needs a dependency or a parser and is disproportionate for one owned block.
- **Writing the rule under a new file name (`rules/gator-loop.rules`):** whether Codex loads every file in `rules/` was not verified. `default.rules` was.
- **Refusing unverified Codex versions:** too brittle; the per-launch `execpolicy` proof is the real guard.

## Changes

### 1. Launcher module (new)
- File: `src/gator_command/scripts/loop/codex_launcher.py`.
- What:
  - Constants: `RULE_TEXT`, `KNOWN_GENERATED_RULES`, `BLOCK_BEGIN` / `BLOCK_END`, `VERIFIED_CODEX_VERSION = "0.144.1"`, `MANUAL_NOTE = "reference-notes/codex-routine-participant-profile.md"`, `TRUST_WARNING`, `SIGN_IN_NOTE`.
  - `class ProfileError(Exception)` carries a user-facing message plus the manual-note pointer.
  - `default_home()`, `validate_home(home, repo_root, env)`, `trust_key(repo_root, platform)`.
  - `render_config(existing_text, repo_key, platform)` returns the new text or raises `ProfileError`. Pure.
  - `plan_preparation(home, repo_root, platform)` returns a list of `(action, path, content_or_None)`. Read-only.
  - `apply_preparation(plan)`: create dirs, write files (UTF-8, no BOM, atomic via temp file + `os.replace`).
  - `check_policy(codex, rules_path, env, run)`.
  - `codex_version(codex, run)`.
  - `launch(codex, repo_root, home, run)` returns the return code.
  - `main(args, *, env=os.environ, platform=sys.platform, which=shutil.which, run=subprocess.run, cwd=None)` orchestrates and returns an exit code. The injected seams make it testable without Codex.
- Why: Sketch "Minimal Design" and "Idempotent preparation" steps 1–6.

### 2. CLI routing
- File: `src/gator_command/scripts/loop/cli.py`.
- What: add a `codex` subparser ("Launch Codex with the opt-in loop participant profile (see codex-routine-participant-profile.md)") with `--dry-run` and `--home`. `_cmd_codex(args)` lazily imports `codex_launcher` and calls `sys.exit(codex_launcher.main(args))`. Add `"codex": _cmd_codex` to the dispatch table.
- Why: the sketch's command surface. Lazy import keeps every other subcommand unaffected.

### 3. Packaging
- File: `pyproject.toml`.
- What: add `"scripts/loop/codex_launcher.py"` to package-data, per the cross-cutting rule; `tests/test_packaging.py` guards this.

### 4. Reference note (template + dogfood, byte-identical)
- Files: `src/gator_command/templates/gator-starter/reference-notes/codex-routine-participant-profile.md` and `.gator/.includes/reference-notes/codex-routine-participant-profile.md`.
- What: a new "Quick Setup: `gator loop codex`" section before Setup. It covers:
  - what the command does and does not do (no join, no token, no Goal mode);
  - the default home and `--home`;
  - `--dry-run`;
  - the first-use sign-in note;
  - the flow `gator loop codex` → `gator loop join` → `/goal`;
  - the fail-closed cases (they point back to the manual Setup);
  - Windows-only support and the version warning;
  - removal: delete `~/.gator/adapters/codex/loop-home/`.
  
  The manual Setup stays as the fallback for unverified surfaces.

## Dependencies and Ordering

- **1 → 2:** the launcher functions exist and are tested before CLI routing.
- **3 and 4** land with 2, because the subcommand becomes public there.
- No change touches loop state, tokens, the protocol or the Dashboard.

## Assumptions, Risks, and Required Architect Decisions

- **Assumption (non-blocking):** the dedicated home is a valid opt-in only on **Windows** in this release, because only Windows was verified. Other OSes get the manual-note pointer. Reversible: add platforms after running the checklist.
- **Assumption (non-blocking):** an unverified Codex version warns but proceeds, because `execpolicy` proves the boundary on every launch.
- **Assumption (non-blocking):** the trust key uses Codex's own lowercase Windows form (§8.8). If Codex normalizes differently, the visible effect is one Codex trust prompt, after which Codex appends its own entry **in the dedicated home**. That is harmless: the normal home is never used. `--dry-run` shows the key.
- **Assumption (non-blocking):** printing the trust entry before writing satisfies "after showing it to the user". There is no interactive confirmation, because running `gator loop codex` is itself the explicit opt-in.
- **Boundary note (charter):** `scripts-loop.md` "Does Not Own: Auto-launching of agent sessions" is narrowed to "except the explicit, opt-in `gator loop codex` launcher, which starts an interactive Codex session but never starts, joins, or authorizes a loop". The sketch authorizes this command, so no escalation is needed; it is flagged for the significance check at commit.
- **Risk:** the `.CMD` shim. `codex` resolves to `codex.CMD` (npm). Python's list-form `subprocess.run` launches `.cmd` files through `cmd.exe` implicitly. Our argv is fixed (no user-supplied arguments, no token), so the batch-argument escaping class does not apply.
- **Risk:** the Codex config schema may change in later versions. Fail-closed parsing plus the `tomllib` check (3.11+) contain it.
- **No blocking Architect decision identified.**

## Testing

Every test injects `env`, `platform`, `which` and `run`; none launches a real interactive Codex. New file `tests/test_loop_codex_launcher.py`.

- **Preparation (checkpoint 1):**
  1. **Fresh home → exact files.** `plan_preparation` + `apply_preparation` on a temp home produce only `rules/default.rules` (bytes == `RULE_TEXT`, no BOM) and `config.toml` (just our block, with the expected Windows trust key and `[windows]`). Nothing else exists.
  2. **Idempotent and preserving.** A second preparation is a no-op. With user content (`model = "x"` above the block and `[profiles.p]` after it), regeneration keeps every user byte and keeps our block last. A second repo adds a second trust entry to our block.
  3. **Fail-closed matrix** (one parameterized test; `ProfileError` and no writes in each case):
     - an unfamiliar `default.rules`;
     - an extra file in `rules/`;
     - a user `[windows]` outside the block;
     - a user `[projects.'<same key>']` outside the block;
     - a malformed block (begin without end);
     - a repo path containing `'`.
  4. **Home validation** (parameterized; refuses each): the normal `~/.codex`, the caller's `CODEX_HOME`, a home inside the repo, a home under the temp directory.
  5. **`--dry-run` is read-only.** A directory snapshot of the home and repo is unchanged, `run` is never called, and the printed output contains the home, the rule text, the trust entry and the launch argv.
- **Verification and launch (checkpoint 2):**
  6. **Policy proof gate.** A fake `run` returns the real-format JSON. Pass case: `allow` / `[]` / `[]` lets it proceed. Parameterized fail cases each stop before launch with no launch call: covered not `allow`; `git write-tree` matched; `gator loop end` matched; non-zero exit; non-JSON output.
  7. **Child-only `CODEX_HOME`.** The launch argv is exactly `[codex_path]`, `cwd == repo_root` and `env["CODEX_HOME"] == home`. The parent `os.environ` is unchanged after `main()`, and `main()` returns the fake child's return code (e.g. 7).
  8. **Clear non-destructive refusals** (parameterized): codex missing, non-Windows platform, and not a governed repo. Each returns non-zero with the manual-note pointer and writes nothing.
  9. **First-use and recovery messages.** No `auth.json` → the sign-in note printed before launch. Non-zero exit with `auth.json` still absent → the recovery hint with the resolved `CODEX_HOME` and `codex login`. The existence check never opens the file.
  10. **CLI routing.** `gator loop codex --dry-run --home <tmp>` through `loop.cli.main` reaches the launcher. Other subcommands are untouched (existing `tests/test_loop.py` passes).
  11. **Real-Codex integration** (`pytest.mark.skipif(shutil.which("codex") is None)`): write `RULE_TEXT` to a temp home outside `%TEMP%`, using `tmp_path` only for files and passing `--rules` explicitly, which execpolicy accepts anywhere. Run the real `check_policy` and assert it passes. This pins that the canonical rule still parses and keeps the boundary on the installed Codex.
- **Doc pair:** a byte-identity assertion for the reference-note pair, added to the existing `TestParticipantDocs`-style guard if one covers this note, otherwise one assertion in the new test file.
- **Final approval:** `python -m pytest tests -q` once. Per checkpoint: the new test file plus `tests/test_loop.py -k "Wait or Protocol"` and `tests/test_packaging.py`.

## Charter Impact

- `scripts-loop.md`:
  - **Covers:** add `loop/codex_launcher.py`.
  - **Owns:** add `codex_launcher.py`: the opt-in Codex participant launcher (dedicated `CODEX_HOME` preparation, the Gator-owned config block, the canonical rule, the `execpolicy` proof and the child-only launch). `cli.py` now routes 17 subcommands.
  - **Does Not Own:** narrow "Auto-launching of agent sessions" as above.
  - New entries for `plan_preparation` / `apply_preparation`, `render_config`, `check_policy`, `launch` and `main`, with tripwires:
    - never read the normal Codex home;
    - never accept or pass tokens;
    - the env change is child-only;
    - unfamiliar rules and config conflicts fail closed;
    - the canonical rule must stay byte-identical to the reference note.
  - `main(argv)`: 17 subcommands.
- `scripts-cross-cutting.md`: the Package and License Surface example list gains `scripts/loop/codex_launcher.py`. The Shipped-Copy section records the reference-note pair and the `RULE_TEXT` ↔ note rule-text pin.

## Coding Checkpoints

1. **Dedicated profile preparation** — Add `codex_launcher.py` with home resolution and validation, the trust key, the canonical rule ownership, the Gator-owned `config.toml` block renderer with fail-closed conflict detection, and read-only plan versus apply. Add `--dry-run` rendering of the plan, and `codex_launcher.py` to `package-data`. Update the loop and cross-cutting charters. Verify: `pytest tests/test_loop_codex_launcher.py -k "prepar or config or home or dry_run"` and `tests/test_packaging.py`.
2. **Verified launch and command surface** — Add the `execpolicy` proof gate, Codex resolution, the version warning, platform refusal, the trust warning and first-use/recovery notes, and the child-only `CODEX_HOME` launch returning Codex's exit status. Wire `gator loop codex [--dry-run] [--home]` in `cli.py`. Add the "Quick Setup" section to both reference-note copies. Update the loop charter. Verify: `pytest tests/test_loop_codex_launcher.py tests/test_loop.py tests/test_packaging.py`, including the real-`codex execpolicy` integration test when Codex is installed; then `python -m pytest tests -q` once at final approval.
