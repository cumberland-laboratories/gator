# Implementation Plan: Retry-Safe Pre-Commit Override Approval (#34, #35)

## Executive Summary

- **What**: Replace the consume-on-entry override flow with a tree-bound block/approval state machine. The state machine lives in a new shared module `precommit_override.py`, and `gator-pre-commit.py` and `gator-approve.py` both use it.
- **Key decision**: Pre-commit evaluates all rules first. Only then does it check an approval, which is bound to the `git write-tree` OID. Nothing is consumed until `post-commit`. Every blocked attempt writes a block record, including attempts with no approvable rule. `approve` therefore always gives a diagnosis instead of "No pending override request".
- **Main risk**: Keeping the starter, dogfood and Enterprise bundled copies in sync, and handling linked worktrees. State is stored under the per-worktree `git rev-parse --git-path` directory, not in the shared `.gator/`.
- **Verification**: Lifecycle integration tests (block → approve → secondary fail → retry → commit → cleanup), plus unit tests for the envelope parsing, gitignore convergence and Dashboard denial.

## Summary

The plan implements the sketch as one state machine with a versioned envelope (`gator-override-v2`). It changes the order of `phase_validate()`, moves consumption into `phase_cleanup()`, and gives every block a resolution class. It also retires the `.gator/.override` bypass, adds durable sanitized trailers, fixes gitignore convergence and Dashboard denial, and syncs the Enterprise bundled copy.

## Approach

**State location.** Transient state lives at `$(git rev-parse --git-path gator-override)/` (for example `.git/gator-override/` or `.git/worktrees/<wt>/gator-override/`). It is not stored in `.gator/`. This one choice does three things:
- It solves linked worktrees, because the path is per-worktree and per-index.
- Git can never stage it.
- The Dashboard cannot serve it, because it is outside the working tree.

Legacy files in `.gator/` (`override-request.json`, `override-approved.json`, `.override-meta.json`, `.override`) are only detected and retired. They are still gitignored and Dashboard-denied as a migration safety net. *Assumption (reversible)*: the Architect accepts moving state out of `.gator/`. If not, fall back to `.gator/` with a per-worktree subdirectory keyed by the `git rev-parse --git-dir` hash.

**Files.**
- `block.json`: schema, block_id, created_at, expires_at (24h), index_tree, failures[{rule, resolution}], files (the complete list; display is truncated separately).
- `approval.json`: block_id, index_tree, expires_at, approved_by, approved_at, reason.
- `handoff.json`: block_id, index_tree, trailer values. Written by validate on a pass and read by commit-msg.

**Resolution classes.**
- `approvable`: charter-alongside-code, cross-cutting-missing, charter-index-gap.
- `fix-required`: frontmatter-parse, invalid-change-type, invalid-significance, empty-commit-draft, missing-message.
- `lint`: HIGH/CRITICAL Layer 1 findings.

**Lint decision (sketch design question).** Fold HIGH/CRITICAL lint into the envelope as `approvable`. The approval then covers the exact tree, and one audit model applies. `lint-allow.json` stays as a read-only compatibility input for one release. A non-empty `lint-allow.json` produces a deprecation warning and is still honored only when an envelope approval for the same tree also exists. Otherwise it produces a diagnostic. This removes the unscoped path without breaking existing repos silently.

**Status/cancel (sketch assessment).** Include `gator hook override status` and `gator hook override cancel` in this slice. They are cheap once the shared module exists, and they fix the "abandoned request" ambiguity. `gator hook approve` stays as an alias of `override approve`. Approval stays Architect-only, with the existing interactive confirmation and a minimum 10-second delay.

**Validate order (new `phase_validate`).**
1. Compute `tree = git write-tree`, then evaluate hard rules with `override=None`, then run lint.
2. Load the state with `precommit_override.inspect(state_dir)`. It returns a discriminated result: `absent`, `malformed`, `legacy`, `expired`, `mismatch`, or `valid`.
3. If the state is `valid`, and approval.index_tree equals the tree, and the approval's block covers all current `approvable` failures, remove those failures.
4. If failures remain, write or refresh `block.json` atomically (temp file + `os.replace`). The block_id stays the same when the tree and failure set are unchanged. On a new tree the block is superseded and the stale approval is deleted. Print the classified output. Exit 1 and **keep a valid approval**.
5. On a pass, write `handoff.json` and exit 0.

**commit-msg.** Reads `handoff.json` and emits these trailers:
- `Gator-Charter-Changed: override-skip`
- `Gator-Override-Approved-By`
- `Gator-Override-Block`
- `Gator-Override-Reason`
- `Gator-Override-Rules`

Values are sanitized: CR/LF are removed, and the approver is capped at 80 characters and the reason at 200. The handoff is not deleted.

**post-commit.** `precommit_override.retire(state_dir)` idempotently removes block, approval and handoff, plus the legacy `.gator/` override files. It runs on every successful commit, so abandoned state is retired as well.

## Changes

### 1. New shared module
- File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`, with a dogfood copy in `.gator/.includes/scripts/` and an Enterprise bundled copy.
- What:
  - Functions: `state_dir(repo_root)`, `index_tree(repo_root)`, `classify(rule)`, `inspect()`, `write_block()`, `write_approval()`, `write_handoff()`, `read_handoff()`, `retire()`, `cancel()`, `sanitize_trailer_value()`.
  - Constants: `SCHEMA = "gator-override-v2"` and `EXPIRY_HOURS = 24`.
- Why: A single interpreter for the JSON, as the sketch §1 requires.

### 2. Pre-commit restructure
- File: `.../gator-starter/scripts/gator-pre-commit.py`
- What:
  - Delete `check_override()`, `_write_override_request()` and the legacy `.override` path.
  - Rewrite the override section of `phase_validate()` to follow the order above.
  - `assemble_trailers()` reads the handoff.
  - `write_whiteboard()` and `build_status()` receive the override from the handoff.
  - `phase_cleanup()` calls `retire()`.
  - If a legacy `.gator/.override` is present, fail with a message naming `gator hook approve`.
  - The block box text names `gator hook approve`, not the stale `python .gator/scripts/gator-approve.py` path. This overlaps with #13.
  - `write_commit_issues()` text points to `gator hook approve` instead of editing `lint-allow.json`.

### 3. Approve CLI
- File: `.../gator-starter/scripts/gator-approve.py`
- What: Add `status` / `cancel` / `approve` subcommands. Parse arguments before any prompt, which fixes #14. The default with no arguments is `approve`.
- `approve` shows the block's age and expiry, whether the current tree still matches, and each failure with its resolution. It refuses when:
  - there are no `approvable` failures (it names the fix-required rules), or
  - the tree has changed (it tells the Architect to retry the commit so a fresh block is written).
- With no block, it says "no blocked attempt recorded" and suggests retrying the commit.

### 4. CLI routing
- File: `src/gator_command/cli.py`
- What: Add the `gator hook override {status,cancel,approve}` route. Keep `gator hook approve` as an alias.

### 5. Lint compatibility
- File: `.../gator-starter/scripts/precommit_lint.py`
- What: Honor `lint-allow.json` only together with an envelope approval, and warn about deprecation.

### 6. Enterprise sync
- File: `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/{gator-pre-commit.py, precommit_override.py, precommit_lint.py}`
- What: Mirror the changes. First step of implementation: grep `tests/` and `contracts/` for byte-identity assertions on these files and sync every copy named there.

### 7. Gitignore convergence
- File: `src/gator_command/scripts/gatorize.py`, `ensure_repo_gitignore()`
- What:
  - Add `.gator/commit_issues.md`, `.gator/override-request.json`, `.gator/override-approved.json`, `.gator/.override-meta.json` and `.gator/.override`.
  - **Fix the substring match.** It currently tests `rule not in gi_text`, so `.gator/.override` is falsely "present" whenever `.gator/.override-meta.json` exists. Change it to an exact match on stripped lines.
  - Check that `gator-update.py` reaches this helper on the upgrade path.
  - Stop `phase_validate` from `stage_file()`-ing `commit_issues.md`. This is required once the file is ignored.
- Assumption: `commit_issues.md` becomes untracked. The existing tracked copy is removed with `git rm --cached` during `gator update`.

### 8. Dashboard denial
- File: `src/gator_command/scripts/dashboard/content_policy.py`
- What: Add the undotted `override-request.json` and `override-approved.json` to `_DENIED_EXACT_BASENAMES`, plus `.override`, and keep the dotted aliases. Fix the seed in `tests/test_dashboard_ui/content_transport_seed.py` to use the real names, and cover listing, `/file`, `/raw` and historical reads.

### 9. Guidance
- Files:
  - `src/gator_command/templates/gator-starter/commands/commit.md` and `.claude/commands/commit.md`: remove the instruction to create `.gator/.override`.
  - `.gator/.includes/procedures/architect-override.md` and its starter copy: rewrite around status/approve/cancel, add the file matrix, fix relative links.
  - `.gator/blueprints/commit-pipeline.md`.
  - `docs/governance-model.md`.
  - expected-governance-residue and committing-gator-files guidance.

### 10. Trailer readers
- Files: `src/gator_command/scripts/gator-audit.py`, `gator-repo-status.py`
- What: Accept the new `Gator-Override-Reason` and `Gator-Override-Rules` trailers additively. Existing readers ignore unknown trailers, which needs verifying.

## Dependencies and Ordering

1. Create module 1, then write its unit tests.
2. Change 2 and change 3 depend on 1. Change 4 depends on 3.
3. Change 5 depends on 1.
4. Change 6 comes after 1, 2 and 5 are final.
5. Changes 7 and 8 are independent and can go in parallel.
6. Changes 9 and 10 come last.

Everything ships in a single commit series on `dev`. The repo copies stay synchronized at each commit.

## Assumptions, Risks, and Required Architect Decisions

- **Non-blocking assumption**: State moves to the git-path directory (see Approach). This is reversible.
- **Non-blocking assumption**: Lint is folded into the envelope, and `lint-allow.json` is kept for one release as a compatibility path that only works with an envelope approval.
- **Non-blocking assumption**: The expiry is 24 hours.
- **Non-blocking assumption**: `commit_issues.md` becomes untracked.
- **Risk**: `git write-tree` fails when the index has unmerged entries. In that case, fail closed with the message "resolve merge conflicts first".
- **Risk**: `git commit -a` and `--amend` stage content during the commit. The tree is computed inside pre-commit, so it reflects the real index. `--amend` needs a test.
- **Risk**: The runtime pin means fleet repos pick up the change only after `gator update`. The old `.gator/` files are retired on the first successful commit under the new runtime.
- No blocking Architect decisions.

## Testing

New file `tests/test_precommit_override.py` covers:
- Unit tests: envelope parse/validate for absent, malformed, legacy, expired and mismatch states, `classify()`, sanitization (CR/LF, length, fake `Gator-` prefix), and atomic supersede.
- Integration tests on a temp git repo:
  - **Sketch 1**: charter block + invalid change-type → approve → retry. The approval is still present, and the output names `invalid-change-type (fix-required)`. After fixing and retrying, the commit lands.
  - **Sketch 2**: unchanged tree → commit → the state dir is empty and the legacy files are gone.
  - **Sketch 3**: modify, add, delete, rename or restage → approval rejected with a mismatch message. Expired, malformed and abandoned state cannot authorize.
  - **Sketch 4**: `commit-msg` failure injected by an env hook, or `git commit` aborted with an empty message → retry works with the same approval.
  - **Sketch 5**: a new block supersedes the old one, `cancel` clears state, and `status` output is checked.
  - **Sketch 6**: the approver/reason trailers are correct in `git log`, cannot be injected, and `gator-audit` parses them.
  - **Sketch 7**: gitignore convergence on an existing `.gitignore` (including the substring bug), Dashboard denial across list/file/raw, a legacy `.override` causes a block with guidance, the Enterprise copy stays in sync, and a linked worktree keeps separate state.
- Existing suites to run: `tests/test_gatorize.py`, `tests/test_dashboard_ui/`, `contracts/compatibility/`, and every pre-commit/hook test.

## Charter Impact

- **New charter** `scripts-precommit.md`, covering `gator-pre-commit.py`, `precommit_*.py` and `gator-approve.py`. These currently map only to Cross-Cutting in `INDEX.md` and have no function-level charter. It documents the state machine, a TRIPWIRE on consume-only-in-post-commit, and a TRIPWIRE on tree binding. Update `INDEX.md` line 26.
- `scripts-cross-cutting.md`: add the new trailers to the CLI/Git compatibility tripwire, and add `precommit_override.py` to the shipped-copy synchronization list.
- `scripts-installer.md`: `ensure_repo_gitignore()` switches to exact-line matching and gets the new entries.
- `scripts-dashboard.md`: update the denylist in the `is_browsable()` entry.
- `scripts-managed-state.md` / `gator_layout.RUNTIME_FILES`: review `commit_issues.md` and `lint-allow.json` classification.
