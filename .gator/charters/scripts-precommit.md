# Charter: Pre-Commit Governance and Override Approval

**Covers**: starter `scripts/gator-pre-commit.py`, `scripts/precommit_override.py`, `scripts/precommit_lint.py`, `scripts/precommit_charter.py`, `scripts/precommit_session.py`, `scripts/gator-approve.py` under `src/gator_command/templates/gator-starter/`, and the synchronized Enterprise bundled copies.

Read [`scripts-cross-cutting.md`](scripts-cross-cutting.md) first. This charter owns the commit gate: rule evaluation, the block/approval envelope, trailer assembly, and post-commit cleanup.

## Owns

- `validate` / `trailers` / `cleanup` phases run by the `pre-commit`, `commit-msg`, and `post-commit` hooks.
- The tree-bound override state machine (#34, #35): block records, Architect approvals, the validate→commit-msg handoff, and retirement.
- The Architect override CLI (`gator hook override status|approve|cancel`, alias `gator hook approve`).

## Does Not Own

- Hook dispatch and runtime selection — [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md) (`gator-hook.py`).
- Charter-surface resolution — `gator_core.resolve_charter_surface()` ([`scripts-cross-cutting.md`](scripts-cross-cutting.md)).
- Session snippets and ledger — [`scripts-session-archaeology.md`](scripts-session-archaeology.md).

## TRIPWIRE: Approval Is Bound to One Exact Staged Change

An approval authorizes one staged-change identity (`index_tree()`: SHA-256 over every `git ls-files --stage` entry — mode, blob OID, path) and a named set of rules. Any staged add, delete, rename, mode/content edit, or restage of different content changes it, and the approval stops authorizing (`inspect()` → `mismatch`). Never bind authorization to a filename list, a block ID alone, or a truncated display list.

`HOOK_MANAGED_PATHS` (`.gator/status.json`, `whiteboard.md`, `commit_issues.md`, `lint-allow.json`, `commit_draft.md`) are excluded: the hooks stage the first four themselves during an attempt (with timestamps), and fixing a fix-required finding means editing `commit_draft.md`. Including them would make every retry look like a different change and silently drop the commit-msg handoff. Do not add user-authored content to this set.

## TRIPWIRE: Consumed Only After the Commit Exists

`validate` never deletes or rewrites an approval. A retry blocked for another reason keeps it; `commit-msg` reads the handoff without consuming it; only `post-commit` (`retire()`) removes block, approval, and handoff. Consuming earlier recreates #35: a second, different block becomes un-approvable because the first approval was already spent.

## TRIPWIRE: Every Blocked Attempt Is Diagnosable

A strict-mode block always writes `block.json` with every failed rule and its resolution class (`approvable`, `lint`, `fix-required`) — including attempts with no approvable rule. `gator hook approve` / `override status` must never answer "no pending request" while the last attempt was blocked; they name each rule and what resolves it.

## TRIPWIRE: Validate the Whole Envelope at the Read Boundary

`read_block()`, `read_approval()`, and `read_handoff()` accept a record only if it is JSON with `schema == "gator-override-v2"` AND every required field is present with the right type (`_BLOCK_FIELDS`, `_APPROVAL_FIELDS`, `_HANDOFF_FIELDS`, `_valid_failures()`; numbers exclude bool). Anything else is `malformed` (handoff: `None`). Downstream code indexes fields directly, so a partial or mistyped record must never reach it — a hook must fail closed with a diagnostic, never raise a traceback. Add new fields to these tables when the envelope grows.

## State Files

Per-worktree directory `$(git rev-parse --git-path gator-override)/` — outside the working tree (never staged, never Dashboard-served), and separate per linked worktree.

| File | Written by | Read by | Removed by |
|---|---|---|---|
| `block.json` | validate (each blocked attempt) | approve / status | post-commit `retire()`, `cancel()` |
| `approval.json` | `gator hook approve` (immutable) | validate `inspect()` | post-commit, cancel, validate on mismatch/expiry/malformed/premature |
| `handoff.json` | validate on a pass that used an approval | commit-msg (trailers) | post-commit, cancel, validate on a pass without override |

Legacy v1 files in `.gator/` (`override-request.json`, `override-approved.json`, `.override-meta.json`, `.override`) are never interpreted; `retire()` removes them.

---

### resolve_repo_root(cwd=None) / state_dir(repo_root) / index_tree(repo_root)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Location primitives. `resolve_repo_root` = `git rev-parse --show-toplevel` that must contain `.gator/`; `state_dir` = `git rev-parse --git-path gator-override` resolved against the root; `index_tree` = staged-change digest over `git ls-files --stage -z` minus `HOOK_MANAGED_PATHS` (see the tripwire).
Filesystem: none (git subprocess)
<- `gator-pre-commit.py` phases, `gator-approve.py`
! All three raise `OverrideStateError` rather than guessing: outside a worktree, ungoverned repo, or an index with unmerged entries ("resolve merge conflicts first"). Callers fail closed.

### classify(rule, lint_rules=()) / is_approvable(resolution) / approvable_rules(block)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Resolution classes: `APPROVABLE_RULES` (charter-alongside-code, cross-cutting-missing, charter-index-gap) → `approvable`; rules in `lint_rules` (HIGH/CRITICAL Layer 1 findings of this attempt) → `lint`; everything else → `fix-required`.
<- `write_block()`, `gator-approve.py`
! Unknown rules fail closed to `fix-required`. `FIX_REQUIRED_RULES` lists the known correctness rules (frontmatter-parse, invalid-change-type, invalid-significance, empty-commit-draft, missing-message, legacy-override-file, unmerged-index) for documentation and tests.

### write_block(sdir, tree, failures, files, lint_rules=(), now=None) / read_block(sdir)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Atomic (temp + `os.replace`) `block.json`: `schema`, `block_id`, created/updated/expires (24 h, `EXPIRY_HOURS`), `index_tree`, `failures[{rule, resolution, message}]`, and the complete sorted `files` list.
Filesystem: `<git-path>/gator-override/block.json` (RW)
<- `gator-pre-commit.phase_validate()`
! `block_id` is stable for the life of one tree (kept while `index_tree` matches and the block is unexpired) and independent of the failure set; a new tree gets a new random id.

### write_approval(sdir, block, approved_by, reason, now=None) / read_approval(sdir) / retire_approval(sdir)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Immutable approval snapshot `{approval_id, block_id, index_tree, approved_rules, approved_by, reason, approved_epoch, expires_epoch}` covering every approvable rule of the block. `read_approval` rejects wrong schema or missing fields as `malformed`.
Filesystem: `<git-path>/gator-override/approval.json` (W by approve, R by validate)
<- `gator-approve.py` (write), `inspect()` (read), `phase_validate()` (retire on invalid states)
! Requires non-blank name and reason and at least one approvable rule (`ValueError`). Validate never rewrites it.

### inspect(sdir, tree, now=None)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Read-only discriminated result: `absent`, `malformed`, `expired`, `mismatch` (different tree), `premature` (approval written < `MIN_APPROVAL_DELAY_SECONDS` = 10 s after the block — the carried-over self-approval guard), or `valid`.
<- `gator-pre-commit.phase_validate()`, `gator-approve.py status`
! Only `valid` authorizes; every other state fails closed with its `detail`.

### write_handoff(sdir, approval, overridden_rules, now=None) / read_handoff(sdir, tree=None) / clear_handoff(sdir) / override_trailers(handoff)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Validate→commit-msg handoff for a pass that used an approval: block/approval ids, tree, `overridden_rules`, `charter_override`, and sanitized approver/reason. `read_handoff(tree=...)` ignores a handoff for a different tree. `override_trailers()` renders `Gator-Override-Approved-By`, `-Block`, `-Reason`, `-Rules`.
Filesystem: `<git-path>/gator-override/handoff.json` (RW)
<- `phase_validate()` (write/clear), `phase_trailers()` / `assemble_trailers()` (read)
! Values pass through `sanitize_trailer_value()` (CR/LF collapsed, whitespace normalized, approver ≤ 80, reason ≤ 200 chars) so Architect input cannot inject extra trailers.

### retire(sdir, gator_dir=None) / cancel(sdir) / legacy_files_present(gator_dir)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Idempotent removal of block, approval, handoff (and, with `gator_dir`, the four legacy v1 files). `cancel()` = retire without the legacy sweep.
<- `phase_cleanup()` (every successful commit, so abandoned state is retired too), `gator-approve.py cancel`
! Cancellation is not approval and is safe for agent or Architect; approval remains Architect-only.

### phase_validate()
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
`pre-commit` hook. Order: (1) `index_tree()` + `state_dir()` (an OverrideStateError becomes an `unmerged-index` fix-required failure); (2) `validate_hard_rules()` with **no** override, soft rules, a `legacy-override-file` failure if `.gator/.override` exists, then Layer 1 lint (HIGH/CRITICAL become failures; their rule names form `lint_rules`; a non-empty `lint-allow.json` adds a `lint-allow-deprecated` warning); (3) `override_state.apply_approval()`: `expired`/`mismatch`/`malformed`/`premature` retire the approval with a note, `valid` removes only failures whose rule is in `approved_rules` AND classifies approvable/lint; (4) warn mode moves failures to warnings; (5) status.json + whiteboard (both receive the handoff); (6) blocked → `write_block()` with ALL pre-approval failures, then `render_block_report()` (per-rule `[resolution]`, Resolution summary, STOP box naming `gator hook approve` only when something is approvable, `Block ID` + `gator hook override status` pointer), exit 1; (7) pass → `write_handoff()` only when an approval covered failures, clears `lint-allow.json`, prints the OVERRIDE line, exit 0.
Filesystem: `.gator/status.json`, `.gator/whiteboard.md` (W + staged), `.gator/commit_issues.md` (W only — hook-transient and gitignored, never staged, #34), override state dir (RW)
<- `pre-commit` hook via `gator-hook.py`
-> `validate_hard_rules()`, `validate_soft_rules()`, `run_layer1_lint()`, `override_state.*`, `build_status()`, `write_whiteboard()`
! Never deletes or rewrites `approval.json` except to retire an invalid one. A secondary block (e.g. `invalid-change-type` after a charter approval) keeps the valid approval and says so — the #35 fix.
! The block lists every current failure including approval-covered ones, so re-running `approve` produces a snapshot covering all approvable rules (supersede matrix: a new approvable rule keeps the old approval and is reported as needing approval).
! `validate_hard_rules(..., override=None)` keeps its `override` parameter for compatibility; validate always passes None.

### phase_trailers(msg_file_path) / assemble_trailers(frontmatter, body, gator_dir, staged_files, override=None, handoff=None)
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
`commit-msg` hook. Reads the handoff for the **current** tree (`read_handoff(tree=index_tree())`) without consuming it. `assemble_trailers()` emits `Gator-Charter-Changed: override-skip` when the handoff overrode a charter rule (else yes/no), then `override_state.override_trailers(handoff)` (`Gator-Override-Approved-By`, `-Block`, `-Reason`, `-Rules`, sanitized).
<- `commit-msg` hook
! `override` parameter is retained for signature compatibility and ignored. No `.override-meta.json` side file exists any more.

### build_status(gator_dir, staged_files, frontmatter, body, handoff=None) / write_whiteboard(gator_dir, failures, warnings, handoff, enforcement_level)
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
Status snapshot and whiteboard. A charter-override handoff records `charter_changed: "override-skip"`; the whiteboard `## Overrides` line names the overridden rules, approver, reason, and block id from the handoff.
<- `phase_validate()`

### phase_cleanup()
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
`post-commit` hook: snippet emission, commit_draft reset, whiteboard reset, then `override_state.retire(state_dir, gator_dir)` — the only place override state is consumed; also retires abandoned state and legacy v1 files. Guarded so cleanup can never fail a landed commit.
<- `post-commit` hook

### run_layer1_lint(staged_files, repo_root) / load_lint_allowlist(gator_dir)
File: `src/gator_command/templates/gator-starter/scripts/precommit_lint.py`
Layer 1 mechanical lint over ADDED lines (plus dangerous staged filenames). Returns every finding with `rule`, `severity` (context-aware via `_effective_severity()`), `file`, `line`, `message`, optional `match`, and `allowlisted` (True when the deprecated `.gator/lint-allow.json` lists `(rule, file)`).
Filesystem: git diff (R), staged files (R), `.gator/lint-allow.json` (R)
<- `phase_validate()`
! **The allowlist no longer suppresses findings (#34).** An unscoped `(rule, file)` entry was a content-independent bypass of HIGH/CRITICAL lint. HIGH/CRITICAL findings now become `lint`-class failures that clear only via an Architect approval bound to the exact staged change; `phase_validate()` emits a `lint-allow-deprecated` warning when the file is non-empty, naming listed findings that still block. The file is a **read-only** compatibility input for one deprecation release: the hook never rewrites or stages it (the former `clear_lint_allowlist()` pass-path reset was retired — it silently edited user config on unrelated commits). Pinned by `test_lint_allow_json_is_never_rewritten_or_staged`.
! Byte-identical with the Enterprise bundled copy (`TestByteIdentityAcrossThreeCopies`).

### write_commit_issues(gator_dir, findings)
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
Lint findings file. Guidance now says HIGH/CRITICAL findings are fixed or Architect-approved via `gator hook approve` for the exact staged change (no longer "the agent edits lint-allow.json").

### main(argv) / cmd_status() / cmd_approve() / cmd_cancel() / build_parser()
File: `src/gator_command/templates/gator-starter/scripts/gator-approve.py`
Architect override CLI. argparse runs before any prompt (#14). No subcommand, or leading flags (v1 `--reason/--name` usage), normalizes to `approve`; unknown subcommands are argparse usage errors (exit 2). Root/state/tree come from `precommit_override` (`resolve_repo_root()` works from a governed subdirectory or a linked worktree; errors exit 1).
- `status`: `describe()` of the last block + approval state from `inspect()` + any legacy v1 files. Exit 0.
- `approve`: never says "no pending request" for a recorded block. Refuses (exit 1) with a specific reason when: no block recorded (tells the Architect to retry the commit), block malformed (cancel + retry), staged tree changed since the block (retry to refresh), block expired, nothing approvable (names the fix-required rules), or block younger than `MIN_APPROVAL_DELAY_SECONDS`. Otherwise prompts only for a missing `--reason` / `--name`, writes the immutable snapshot via `write_approval()`, and states any remaining fix-required findings.
- `cancel`: `precommit_override.cancel()`; reports what was removed. Exit 0.
Filesystem: override state dir via `precommit_override` only
<- `gator-hook.py` (`override`, alias `approve`)
! `approve` is ARCHITECT-ONLY (constitution). `status` and `cancel` are safe for anyone. Tests exercise `approve` only in throwaway temp repos, never against a real repo's block.

### apply_approval(sdir, tree, failures, lint_rules=()) / render_block_report(header, failures, warnings, lint_rules, notes, block, info_lines=())
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
The ONE approval decision and the ONE blocked-attempt report, shared by every validate path — strict mode in both pre-commit copies and the Enterprise `evidence_only` lint path — so they cannot diverge. `apply_approval` clears a stale handoff, retires an expired/mismatch/malformed/premature approval (note), removes only failures whose rule the valid approval names AND that classify approvable/lint, writes the handoff when nothing remains, and returns `(remaining, handoff, notes)`; it never deletes a valid approval. `render_block_report` returns the tagged failures, warnings, notes, info lines, the fix-required vs approvable Resolution summary, the Architect STOP box (only when something is approvable), and the Block ID pointer.
<- `gator-pre-commit.phase_validate()` (template + bundled strict path), bundled `evidence_only` branch
! New validate paths must call these rather than re-implementing approval application or the report.

### describe(block, approval, tree, now=None)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Shared status text: block id, age, expiry, whether the current tree still matches, each failure with its resolution, files, and any approval.
<- `gator-approve.py`

## Delivery (where these scripts run)

| Runtime | Source | Reaches a repo via | Pin |
|---|---|---|---|
| Wheel runtime (canonical) | `src/gator_command/templates/gator-starter/scripts/` | Not copied; `gator-hook.py` runs the wheel's template scripts and siblings resolve from the same dir | `pyproject.toml` package-data `templates/**/*` |
| Enterprise bundled | `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/` | `repo_init._install_bundled_scripts()` copies every `*.py` to `.gator/scripts/` | byte-identity + install self-sufficiency tests (see [`scripts-enterprise-cli.md`](scripts-enterprise-cli.md)) |
| Repo-resident `.gator/.includes/scripts/` | Retired (runtime-split Phase 4) | Not shipped | — |

When a sibling module is added or its semantics change, change the Enterprise bundled copy in the same commit.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) — trailer compatibility, shipped-copy synchronization
-> [Session Boot and Hook Dispatch](scripts-repo-lifecycle.md) — `gator-hook.py` routes `override` / `approve`
-> [Session Archaeology](scripts-session-archaeology.md) — snippet emission in cleanup
