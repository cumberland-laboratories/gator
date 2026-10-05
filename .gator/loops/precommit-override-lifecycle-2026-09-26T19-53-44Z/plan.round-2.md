# Implementation Plan: Retry-Safe Pre-Commit Override Approval (#34, #35)

## Executive Summary

- **What**: Replace the consume-on-entry override flow with a tree-bound block/approval state machine. The state machine lives in a new shared module `precommit_override.py`, and `gator-pre-commit.py` and `gator-approve.py` both use it.
- **Round 1 revisions**: Approvals are immutable snapshots with a supersede matrix. Routing goes through `gator-hook.py`, and repo-root resolution is explicit.
- **Key decision**: Pre-commit evaluates all rules first. Only then does it check an approval, which is bound to the `git write-tree` OID. Nothing is consumed until `post-commit`. Every blocked attempt writes a block record, including attempts with no approvable rule. `approve` therefore always gives a diagnosis instead of "No pending override request".
- **Main risk**: Keeping the starter, dogfood and Enterprise bundled copies in sync, and handling linked worktrees. State is stored under the per-worktree `git rev-parse --git-path` directory, not in the shared `.gator/`.
- **Verification**: Lifecycle integration tests (block → approve → secondary fail → retry → commit → cleanup), plus unit tests for the envelope parsing, gitignore convergence and Dashboard denial.

## Revision Response (round 1)

- **Finding 1 (High), accepted.** Two changes:
  - **Block identity.** The block ID is now keyed by the index tree only. It is stable for the life of that tree and does not depend on the failure set. `block.json` records the current failures separately and may be refreshed freely.
  - **Approval snapshot.** `approval.json` is an immutable snapshot `{approval_id, block_id, index_tree, approved_rules[], expires_at, approved_by, reason}`. Validate never rewrites it.

  Each event has an explicit effect:

  | Event | Effect |
  |---|---|
  | Tree change | New block ID. The approval no longer matches and is retired. |
  | Expiry | The approval is retired with a diagnostic. |
  | `cancel` | Block and approval are retired. |
  | New approvable rule not in `approved_rules` | The approval is kept and still covers its own rules. Output says the new rule needs approval. Running `approve` again writes a new snapshot covering all current approvable rules. |
  | Fix-required or lint change alone | The approval is kept. |

  Each event gets a test (see Testing).
- **Finding 2 (High), accepted.** The route goes in `gator-hook.py` `HOOK_MAP` (`override` → `gator-approve.py`, forwarding argv). `approve` stays as the alias. `cli.py` is removed from Changes. Dispatcher tests are added.
- **Finding 3 (Medium), accepted.** `precommit_override.resolve_repo_root(cwd)` uses `git rev-parse --show-toplevel`. `git_path()` uses `git rev-parse --git-path gator-override`, resolved against the top level. If either is not a git repo or has no `.gator/`, the command exits 1 with a clear message. Tests cover a governed subdirectory and a linked worktree.

## Revision Response (round 2)

- **Finding 1 (Medium), accepted.** The assumed `.gator/.includes/scripts/` dogfood copy is removed. Change 6 now carries a verified delivery matrix:
  - wheel template (B)
  - Enterprise bundled (C), whose installer copies all `*.py` automatically
  - retired repo-resident copy (A), with no copy added
  - legacy fleet `.gator/scripts/`, not touched

  Each row names its mechanism and test. The matrix also adds an install regression proving that a runtime receiving the changed `gator-pre-commit.py` also receives `precommit_override.py`.

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
3. If the state is `valid` and approval.index_tree equals the tree, remove the current `approvable` failures that are in `approval.approved_rules`. Any approvable failures that remain are reported as "needs approval".
4. If failures remain, write or refresh `block.json` atomically (temp file + `os.replace`). The block_id is keyed by the tree: it is kept while the tree is unchanged and does not depend on the failure set. When the tree changes, a new block_id is created and the stale approval is retired. The approval snapshot is never rewritten by validate. Print the classified output. Exit 1 and **keep a valid approval**.
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
- File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`. The runtime copies are listed in the delivery matrix under Change 6. There is **no** `.gator/.includes/scripts/` dogfood copy.
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

### 4. Hook dispatcher routing
- File: `src/gator_command/scripts/gator-hook.py`, plus any template/dogfood copy named by the sync tests.
- What: Add `override` to `HOOK_MAP`, targeting `gator-approve.py` and forwarding `status|cancel|approve` and any flags. Keep `approve` as the alias, which maps to `gator-approve.py approve`. Unknown subcommands exit 2 with usage. Keep the existing caller-cwd and exit-code contract. `cli.py` is unchanged because it already passes the hook args through.
- Also add `resolve_repo_root(cwd)` and `git_path(root)` in `precommit_override.py`, used by `gator-approve.py` in place of `find_gator_dir()`. They fail with exit 1 and a message outside a git repo or a governed repo.

### 5. Lint compatibility
- File: `.../gator-starter/scripts/precommit_lint.py`
- What: Honor `lint-allow.json` only together with an envelope approval, and warn about deprecation.

### 6. Enterprise sync
- File: `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/{gator-pre-commit.py, precommit_override.py, precommit_lint.py}`
- What: Mirror the changes.

**Delivery matrix (verified, round 2).** Each runtime that can run `gator-pre-commit.py`:

| Runtime | Source of truth | How the scripts reach a repo | Sync test |
|---|---|---|---|
| **B. Wheel runtime** (canonical) | `src/gator_command/templates/gator-starter/scripts/` | Not copied into repos. Since the runtime-split Phase 4 (2026-08-19), the `gator-hook.py` dispatcher runs the installed wheel's template scripts directly, and sibling imports resolve from the same directory. | New: `tests/test_precommit_override.py::test_wheel_ships_override_module`, which checks that the built wheel contains `templates/gator-starter/scripts/precommit_override.py`. It extends the existing installed-wheel coverage. |
| **C. Enterprise bundled** | `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/` | `repo_init._install_bundled_scripts()` copies **every** `*.py` from the bundled directory into `.gator/scripts/`, so a new file is picked up automatically. | Add `precommit_override.py` and `gator-approve.py` to the `TestByteIdentityAcrossThreeCopies` parametrize list in `tests/test_multi_session.py`. New regression: run `_install_bundled_scripts()` into a temp dir and assert that `precommit_override.py` is present next to `gator-pre-commit.py`, and that the installed `gator-pre-commit.py` imports it. |
| **A. Repo-resident `.gator/.includes/scripts/`** | Retired by design (runtime-split Phase 4) | Not shipped by install or update. No copy is added. | None. Adding one would bring back a parallel runtime. |
| **Legacy `.gator/scripts/`** in pre-2.9 fleet repos | Not updated by `gator update` for hook execution, because hooks dispatch to the wheel. | Not changed. | None. |

Before editing, confirm that the `gator-update.py` template-overlay manifest does not also copy `scripts/*.py` into repos. If it does, add the new file to that manifest and add an update regression test, in the same commit as `gator-pre-commit.py`.

`gator-pre-commit.py` itself is still not byte-identical between B and C because of earlier drift. The override section is edited identically in both at the same anchors. Full reconciliation stays out of scope (see the note in `test_multi_session.py`).

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
  - **Supersede matrix** (Finding 1), one test per event:
    - A tree change retires the approval.
    - Expiry retires the approval.
    - `cancel` retires block and approval.
    - A newly introduced approvable rule keeps the approval and reports the new rule as needing approval. Re-approving covers both rules.
    - A fix-required change alone keeps the approval, and the block_id is unchanged.
  - **Dispatcher** (Finding 2):
    - `gator hook override status|cancel|approve` forwards argv.
    - `gator hook approve` alias works.
    - An unknown subcommand exits 2 with usage.
  - **Root resolution** (Finding 3): status/approve/cancel run from a governed subdirectory and from a linked worktree resolve that worktree's state dir. Outside a git repo, the command gives a clear error.
  - **Sketch 6**: the approver/reason trailers are correct in `git log`, cannot be injected, and `gator-audit` parses them.
  - **Sketch 7**: gitignore convergence on an existing `.gitignore` (including the substring bug), Dashboard denial across list/file/raw, a legacy `.override` causes a block with guidance, the Enterprise copy stays in sync, and a linked worktree keeps separate state.
- Existing suites to run: `tests/test_gatorize.py`, `tests/test_dashboard_ui/`, `contracts/compatibility/`, and every pre-commit/hook test.

## Charter Impact

- **New charter** `scripts-precommit.md`, covering `gator-pre-commit.py`, `precommit_*.py` and `gator-approve.py`. These currently map only to Cross-Cutting in `INDEX.md` and have no function-level charter. It documents the state machine, a TRIPWIRE on consume-only-in-post-commit, and a TRIPWIRE on tree binding. Update `INDEX.md` line 26.
- `scripts-cross-cutting.md`: add the new trailers to the CLI/Git compatibility tripwire, and add `precommit_override.py` to the shipped-copy synchronization list.
- `scripts-installer.md`: `ensure_repo_gitignore()` switches to exact-line matching and gets the new entries.
- `scripts-dashboard.md`: update the denylist in the `is_browsable()` entry.
- `scripts-managed-state.md` / `gator_layout.RUNTIME_FILES`: review `commit_issues.md` and `lint-allow.json` classification.
