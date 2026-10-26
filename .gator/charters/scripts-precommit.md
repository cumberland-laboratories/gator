# Charter: Pre-Commit Governance and Override Approval

**Covers**: starter `scripts/gator-pre-commit.py`, `scripts/precommit_override.py`, `scripts/precommit_policy.py`, `scripts/precommit_lint.py`, `scripts/precommit_charter.py`, `scripts/precommit_session.py`, `scripts/gator-approve.py` under `src/gator_command/templates/gator-starter/`, and the synchronized Enterprise bundled copies.

Read [`scripts-cross-cutting.md`](scripts-cross-cutting.md) first. This charter owns the commit gate: rule evaluation, the resolution policy (#75), the block/approval envelope, trailer assembly, and post-commit cleanup.

## Owns

- `validate` / `trailers` / `cleanup` phases run by the `pre-commit`, `commit-msg`, and `post-commit` hooks.
- The closed resolution policy (#75, `precommit_policy.py`): every finding is `fix-required`, `warning`, or `external-approval`.
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

A block always writes `block.json` with every failed rule and its resolution class (`fix-required` or `external-approval`) — including attempts with no approvable rule. `gator hook approve` / `override status` must never answer "no pending request" while the last attempt was blocked; they name each rule and what resolves it. Pre-#75 values (`approvable`, `lint`, `LEGACY_RESOLUTIONS`) are shown as recorded by an earlier runtime and are never approvable.

## TRIPWIRE: Charter Integrity Blocks With an Architect-Only Escape Hatch; Warnings Never Reach the Envelope (#75)

Every correctness rule is `fix-required`. Only a rule that the caller's explicit resolution map names as `external-approval` is approvable: the charter rules (`CHARTER_RULES`, via `precommit_policy.charter_resolutions()`), in every validate path that evaluates them, and HIGH/CRITICAL lint where the mode requires it (`resolution_map()`; Enterprise `evidence_only`). A missing charter update therefore always blocks; the agent updates the charter, and only the Architect may approve the exact staged change when no charter edit is warranted (the escape hatch the #76 Commits approval button relies on). The approval produces `Gator-Charter-Changed: override-skip` plus the `Gator-Override-*` trailers. Under the default policy a HIGH/CRITICAL dangerous finding is a `[warning]`: it is reported (hook output, whiteboard, `status.json` `commit_checks`), never approvable, and never creates override state. While any warning has no recorded decision, validate adds the commit-level `dangerous-pattern-pause` failure (`policy.PAUSE_RULE`, resolution `pause`, mapped into the attempt's resolutions): the commit blocks with the PAUSE box and no approval command. The pause is in `block.json` (so `override status` diagnoses it) but `is_approvable()` is false for it and `apply_approval()` never clears it. It clears only when every warning key is acknowledged (the Architect's decision) or listed in `dangerous-pattern-skips` (a recorded skip, emitted as `Gator-Dangerous-Patterns-Unacknowledged`). Do not infer a resolution from rule-name membership again, and do not add a configuration knob for the category policy as a side effect: that is a separate, explicit feature.

! Matched source text (a finding's `match`) goes only to stdout and the gitignored `commit_issues.md`. The whiteboard and `status.json` are staged on a passing commit, so they carry rule names, `file:line — message` and finding keys only.

## TRIPWIRE: In-Flight Legacy Records Are Cancelled, Never Reinterpreted (#75)

When the strict path sees, for THIS staged tree and unexpired, a block with a legacy resolution, a block that already records `legacy-override-record`, or a well-formed approval without the `RESOLUTION_POLICY` marker (`precommit_override.legacy_records()`), it adds the fix-required `legacy-override-record` failure, skips `apply_approval()` (only `clear_handoff()`), and blocks. The guard's own block keeps the marker, so every unchanged retry blocks until `gator hook override cancel` or a tree change. It never applies, retires, or deletes the legacy approval. Other-tree, expired, and malformed state keeps normal retirement. `evidence_only` does not run the guard: its blocks complete under the unchanged envelope.

## TRIPWIRE: Acknowledgement Evidence Binds to Current Warnings and Is Never an Override (#75)

A kept warning is recorded only by the Architect's decision in `commit_draft.md` (`dangerous-pattern-acknowledgements` + `## Architect acknowledgement`). `precommit_policy.validate_acknowledgements()` accepts it only when every listed key is a current HIGH/CRITICAL `warning` finding of this staged change, listed once, with exactly one non-empty body bullet, and the `architect` field is set (`pi` is not accepted for new evidence). Any problem is the fix-required `invalid-dangerous-pattern-acknowledgement` and acknowledges nothing. Absent evidence is valid as evidence, but an unresolved warning pauses the commit (see the previous tripwire). A recorded skip (`validate_skips()`) needs no Architect name, because it is not the Architect's decision; its keys must be current warnings, listed once, and not also acknowledged, and any problem joins the same fix-required rule. `commit-msg` recomputes the result from the same index, so only evidence that validates now becomes `Gator-Dangerous-Pattern-*` trailers (warn mode can pass invalid evidence as a warning, and then writes no trailer). Acknowledgements never read or write override state, and `Gator-Override-*` stays reserved for external approvals. `commit_draft.md` is in `HOOK_MANAGED_PATHS`, so editing the evidence never changes `index_tree()`.

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

### classify(rule, resolutions=None) / is_approvable(resolution) / approvable_rules(block) / legacy_rules(block)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Resolution classes from the caller's explicit map (#75): a rule mapped to `EXTERNAL_APPROVAL` → `external-approval`; every other rule → `fix-required`. `is_approvable()` is true only for `external-approval`. `legacy_rules()` names a block's failures recorded with a `LEGACY_RESOLUTIONS` value.
<- `write_block()`, `apply_approval()`, `render_block_report()`, `gator-approve.py`
! Unknown rules fail closed to `fix-required`. `FIX_REQUIRED_RULES` lists the known rules for documentation and tests: the correctness rules (frontmatter-parse, invalid-change-type, invalid-significance, empty-commit-draft, missing-message, legacy-override-file, unmerged-index), `legacy-override-record`, and `invalid-dangerous-pattern-acknowledgement`. `CHARTER_RULES` (charter-alongside-code, cross-cutting-missing, charter-index-gap; alias `CHARTER_OVERRIDE_RULES`) are not in it: they are approvable through the caller's map. `APPROVABLE_RULES` was removed.

### legacy_records(sdir, tree, now=None)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Read-only #75 migration guard: the reason string when an unexpired same-tree block carries a legacy resolution or the `legacy-override-record` marker, or an unexpired well-formed same-tree approval lacks `resolution_policy == RESOLUTION_POLICY`; else `None` (also when `sdir`/`tree` is None).
<- `gator-pre-commit.phase_validate()` (strict path, both copies)
! See the In-Flight Legacy Records tripwire. The approval test uses the marker, not the current failures, so a current charter approval is never mistaken for a legacy one (pinned by `test_second_block_keeps_the_approval` and `test_legacy_records`).

### write_block(sdir, tree, failures, files, resolutions=None, now=None) / read_block(sdir)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Atomic (temp + `os.replace`) `block.json`: `schema`, `block_id`, created/updated/expires (24 h, `EXPIRY_HOURS`), `index_tree`, `failures[{rule, resolution, message}]`, and the complete sorted `files` list.
Filesystem: `<git-path>/gator-override/block.json` (RW)
<- `gator-pre-commit.phase_validate()`
! `block_id` is stable for the life of one tree (kept while `index_tree` matches and the block is unexpired) and independent of the failure set; a new tree gets a new random id.

### write_approval(sdir, block, approved_by, reason, now=None) / read_approval(sdir) / retire_approval(sdir)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Immutable approval snapshot `{approval_id, block_id, index_tree, approved_rules, approved_by, reason, approved_epoch, expires_epoch, resolution_policy}` covering every approvable rule of the block. `resolution_policy` (`RESOLUTION_POLICY`, #75) is additive and not a required read field; `legacy_records()` uses it to tell this runtime's approvals from earlier ones. `read_approval` rejects wrong schema or missing fields as `malformed`.
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
Validate→commit-msg handoff for a pass that used an approval: block/approval ids, tree, `overridden_rules`, `charter_override` (any overridden rule in `CHARTER_OVERRIDE_RULES`), and sanitized approver/reason. `read_handoff(tree=...)` ignores a handoff for a different tree. `override_trailers()` renders `Gator-Override-Approved-By`, `-Block`, `-Reason`, `-Rules`.
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
`pre-commit` hook. Order: (1) `index_tree()` + `state_dir()` (an OverrideStateError becomes an `unmerged-index` fix-required failure); (2) `validate_hard_rules()` with **no** override, soft rules, a `legacy-override-file` failure if `.gator/.override` exists; (3) the #75 migration guard `legacy_records()` → `legacy-override-record`; (4) Layer 1 lint split by `policy.split_lint(findings, enforcement)`: `dangerous` (HIGH/CRITICAL, `warning`) become the attention list, `external` become failures with `resolutions = policy.resolution_map(external)` (empty in strict), `advisory` (MEDIUM/LOW) become warnings; a non-empty `lint-allow.json` adds `lint-allow-deprecated`; (4a) `policy.validate_acknowledgements(frontmatter, body, dangerous)` and `policy.validate_skips(frontmatter, dangerous, ack_keys)`: problems → one `invalid-dangerous-pattern-acknowledgement` failure; acknowledged and skipped keys leave the attention list; any remaining key → `policy.pause_failure()` plus `resolutions[PAUSE_RULE] = PAUSE`; (5) `override_state.apply_approval(..., resolutions)` (skipped while the guard fires: only `clear_handoff()`); (6) `commit_checks` from `policy.report_categories()` + `finding_keys(dangerous)` + the acknowledged keys and sanitized `acknowledged_by`; (7) warn mode moves failures and attention to warnings; (8) status.json + whiteboard; (9) blocked → `write_block()` with ALL pre-approval failures, then `render_block_report(..., attention=)`, exit 1; (10) pass → a "Kept on the Architect's direction" line for acknowledged keys, a "Committed without an Architect decision (recorded as unacknowledged)" line for skipped keys, the ordinary PASS lines, the OVERRIDE line when a handoff exists, exit 0.
Filesystem: `.gator/status.json`, `.gator/whiteboard.md` (W + staged), `.gator/commit_issues.md` (W only — hook-transient and gitignored, never staged, #34), override state dir (RW)
<- `pre-commit` hook via `gator-hook.py`
-> `validate_hard_rules()`, `validate_soft_rules()`, `run_layer1_lint()`, `override_state.*`, `build_status()`, `write_whiteboard()`
! Never deletes or rewrites `approval.json` except to retire an invalid one. A secondary block keeps the valid approval and says so — the #35 fix, decided once in `apply_approval()`. Example: an approval covers an `external-approval` finding and the retry is still blocked by a fix-required rule (pinned at unit level by `test_apply_approval_keeps_approval_when_fix_required_remains`).
! The block lists every current failure including approval-covered ones, so re-running `approve` produces a snapshot covering all approvable rules (supersede matrix: a new approvable rule keeps the old approval and is reported as needing approval).
! `validate_hard_rules(..., override=None)` keeps its `override` parameter for compatibility; validate always passes None.
! Bundled copy only: the `evidence_only` branch runs lint, `apply_approval(..., resolution_map(lint_failures))` and `write_block()`, and only then writes `status.json` (`commit_checks` with `integrity_failures` = fix-required rules such as `unmerged-index`, `external_approval_required`, `overridden_rules`) and the whiteboard. It stages the whiteboard only when `.gator/whiteboard.md` is already tracked, so an evidence_only repo's committed content is unchanged. Exit decisions are unchanged.


### phase_trailers(msg_file_path) / assemble_trailers(frontmatter, body, gator_dir, staged_files, override=None, handoff=None, acknowledged=None)
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
`commit-msg` hook. Reads the handoff for the **current** tree (`read_handoff(tree=index_tree())`) without consuming it. It reruns Layer 1 lint and `validate_acknowledgements()` for the effective mode (template: `_read_enforcement_level()`; bundled: `GATOR_HOOK_MODE` first) and passes `acknowledged=(keys, architect)` only when there are no problems; ! It fails closed: in the strict path (mode not `warn`, `off` or `evidence_only`), when the draft carries acknowledgement or skip evidence and the recomputation raises or reports problems, `commit-msg` prints "BLOCKED — dangerous-pattern evidence could not be revalidated" and exits 1, so the commit is not created rather than landing without its trailers. Without evidence, an error leaves the trailers alone. Pinned by `test_commit_msg_fails_closed_when_evidence_cannot_be_revalidated`. `assemble_trailers()` appends `policy.acknowledgement_trailers()` after the override trailers. `assemble_trailers()` emits `Gator-Charter-Changed: override-skip` when the handoff overrode a charter rule (else yes/no), then `override_state.override_trailers(handoff)` (`Gator-Override-Approved-By`, `-Block`, `-Reason`, `-Rules`, sanitized).
<- `commit-msg` hook
! `override` parameter is retained for signature compatibility and ignored. No `.override-meta.json` side file exists any more.

### build_status(gator_dir, staged_files, frontmatter, body, handoff=None, checks=None) / empty_commit_checks() / write_whiteboard(gator_dir, failures, warnings, handoff, enforcement_level, resolutions=None, attention=())
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
Status snapshot and whiteboard. `status.json` gains the additive `commit_checks` object (#75): `integrity_failures`, `dangerous_pattern_warnings` (finding keys), `dangerous_pattern_acknowledged`, `acknowledged_by`, `dangerous_pattern_skipped`, `dangerous_pattern_pause` (keys still awaiting a decision), `external_approval_required`, `overridden_rules` (from the handoff). `charter_changed` is `"override-skip"` when the handoff overrode a charter rule, else the boolean. The whiteboard has separate sections: `## Blocked — fix required`, `## External approval required` (split by `policy.report_categories()`), `## Paused — Architect decision required` (the pause failure), `## Dangerous-pattern warnings — Architect attention`, `## Warnings`, `## Architect acknowledgements` (acknowledged keys and the Architect; `acknowledged=`, `acknowledged_by=`), `## Unacknowledged dangerous patterns (recorded skip)` (`skipped=`), and `## Overrides` (rules, approver, reason, block id from the handoff).
<- `phase_validate()` (strict and bundled `evidence_only`)

### phase_cleanup()
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
`post-commit` hook: snippet emission, commit_draft reset, whiteboard reset, then `override_state.retire(state_dir, gator_dir)` — the only place override state is consumed; also retires abandoned state and legacy v1 files. Guarded so cleanup can never fail a landed commit.
<- `post-commit` hook

### run_layer1_lint(staged_files, repo_root) / load_lint_allowlist(gator_dir)
File: `src/gator_command/templates/gator-starter/scripts/precommit_lint.py`
Layer 1 mechanical lint over ADDED lines (plus dangerous staged filenames). Returns every finding with `rule`, `severity` (context-aware via `_effective_severity()`), `file`, `line`, `message`, optional `match`, and `allowlisted` (True when the deprecated `.gator/lint-allow.json` lists `(rule, file)`).
! `parse_diff_added_lines()` drops the single TAB Git appends to a `+++ b/` header path that contains a space, so `file` (and the #75 finding key) names the staged path exactly. Paths Git quotes (`core.quotepath`) do not start with `+++ b/` and are still not linted (pre-existing).
Filesystem: git diff (R), staged files (R), `.gator/lint-allow.json` (R)
<- `phase_validate()`
! **The allowlist no longer suppresses findings (#34).** An unscoped `(rule, file)` entry was a content-independent bypass of HIGH/CRITICAL lint. Since #75 the allowlist also never changes a finding's resolution: under the default policy a listed HIGH/CRITICAL finding is still a `[warning]` (reported, not blocking, no approval command), and under Enterprise `evidence_only` it is still `[external-approval]`, cleared only by an Architect approval bound to the exact staged change. The strict path emits a `lint-allow-deprecated` warning when the file is non-empty, naming listed findings as "still reported"; the bundled `evidence_only` branch adds a note naming them as still blocking. The file is a **read-only** compatibility input for one deprecation release: the hook never rewrites or stages it (the former `clear_lint_allowlist()` pass-path reset was retired — it silently edited user config on unrelated commits). Pinned by `test_lint_allow_json_is_never_rewritten_or_staged`.
! Byte-identical with the Enterprise bundled copy (`TestByteIdentityAcrossThreeCopies`).

### write_commit_issues(gator_dir, findings)
File: `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py`
Lint findings file (gitignored; the only file that carries the matched text). Guidance: HIGH/CRITICAL findings need the Architect's attention (fix, remove, or keep); they do not block and have no approval command, except where an Enterprise mode requires external approval.

### dangerous_resolution(mode) / split_lint(findings, mode) / resolution_map(external_findings) / charter_resolutions(failures) / report_categories(failures, resolutions) / finding_key(finding) / _encode_key_path(path) / finding_keys(findings) / finding_text(finding)
File: `src/gator_command/templates/gator-starter/scripts/precommit_policy.py`
The closed #75 policy table (pure functions, no I/O). `dangerous_resolution`: `evidence_only` → `external-approval`; `strict`/`warn`/`off`/unknown → `warning`. `split_lint` → `(dangerous, external, advisory)`, keeping each finding's fields. `charter_resolutions` → `{rule: external-approval}` for the `CHARTER_RULES` among the failures; validate merges it into the lint map. `report_categories` → `(fix_required, external_approval)` rule lists; a rule the map does not name is fix-required. `finding_key` = `RULE@path:line` (forward slashes, percent-encoded only where needed; line 0 for a dangerous filename), never the matched text.
<- both `gator-pre-commit.py` copies
! Byte-identical with the Enterprise bundled copy (`TestByteIdentityAcrossThreeCopies`). The table has no configuration input on purpose.

### validate_acknowledgements(frontmatter, body, dangerous) / _ack_section(body) / acknowledgement_trailers(keys, architect) / validate_skips(frontmatter, dangerous, acknowledged=()) / skip_trailers(keys) / pause_failure(unresolved_keys)
File: `src/gator_command/templates/gator-starter/scripts/precommit_policy.py`
Architect acknowledgement evidence (#75). `ACK_FIELD` = `dangerous-pattern-acknowledgements` (read through the existing flat `_parse_simple_yaml()` list syntax), `ACK_HEADING` = `## Architect acknowledgement`, `ACK_RULE` = `invalid-dangerous-pattern-acknowledgement`, `KEY_PATTERN` = `RULE@path:line`. `_ack_section()` returns `(present, [(key, text)])` from `- \`KEY\`: text` bullets (indented continuation lines extend the text) until the next `#`/`##` heading. `validate_acknowledgements()` → `(acknowledged_keys, problems)` per the acknowledgement tripwire. `acknowledgement_trailers()` → `Gator-Dangerous-Patterns: <keys joined with ",">` (byte-for-byte: a path may contain spaces, even repeated ones, so internal whitespace is never normalized; only CR/LF become a space; never truncated) and `Gator-Dangerous-Pattern-Acknowledged-By: <architect>` (`precommit_override.sanitize_trailer_value(..., 80)`).
<- `phase_validate()`, `phase_trailers()` (both copies)
-> `precommit_override.sanitize_trailer_value()` / `TRAILER_MAX`
`SKIP_FIELD` = `dangerous-pattern-skips`. `validate_skips()` → `(skipped_keys, problems)`; `skip_trailers()` → `Gator-Dangerous-Patterns-Unacknowledged: <keys>` (byte-for-byte except CR/LF); `pause_failure()` → `(PAUSE_RULE, message naming the unresolved keys, the acknowledgement field and the skip field)` or None. `report_categories()` leaves the pause rule out of both of its lists.
! Every key can be listed: `finding_key()` percent-encodes (`_encode_key_path()`, `_KEY_ESCAPES`) the path characters the flat list, the body bullet or the comma-joined trailer cannot hold (`%` `,` `[` `]` `"` `'` and backtick, control characters, edge spaces). Inner spaces stay byte-for-byte. Pinned by `test_comma_filename_can_clear_the_pause`.

### main(argv) / cmd_status() / cmd_approve() / cmd_cancel() / build_parser()
File: `src/gator_command/templates/gator-starter/scripts/gator-approve.py`
Architect override CLI. argparse runs before any prompt (#14). No subcommand, or leading flags (v1 `--reason/--name` usage), normalizes to `approve`; unknown subcommands are argparse usage errors (exit 2). Root/state/tree come from `precommit_override` (`resolve_repo_root()` works from a governed subdirectory or a linked worktree; errors exit 1).
- `status`: `describe()` of the last block + approval state from `inspect()` + any legacy v1 files. Exit 0.
- `approve`: never says "no pending request" for a recorded block. Refuses (exit 1) with a specific reason when: no block recorded (tells the Architect to retry the commit), block malformed (cancel + retry), staged tree changed since the block (retry to refresh), block expired, the block carries legacy resolutions (`legacy_rules()`: cancel and retry), nothing approvable (names the fix-required rules; dangerous-pattern warnings never use this command), or block younger than `MIN_APPROVAL_DELAY_SECONDS`. Otherwise prompts only for a missing `--reason` / `--name`, writes the immutable snapshot via `write_approval()`, and states any remaining fix-required findings.
- `cancel`: `precommit_override.cancel()`; reports what was removed. Exit 0.
Filesystem: override state dir via `precommit_override` only (plus `_raw_digest()` reading the bytes of an unreadable `block.json` / `approval.json`)
<- `gator-hook.py` (`override`, alias `approve`); the Dashboard override relay (#76) through `gator-hook.py override … --json`
! `approve` is ARCHITECT-ONLY (constitution). `status` and `cancel` are safe for anyone. Tests exercise `approve` only in throwaway temp repos, never against a real repo's block.

### _approval_refusal(snap, tree, now, expect_block=None, expect_revision=None) / _guard_refusal() / _snapshot(sdir) / _revision(block_part, approval_part) / _raw_digest(path) / _status_record() / _approve_json() — machine-readable mode (#76)
File: `src/gator_command/templates/gator-starter/scripts/gator-approve.py`
`--json` on `status`, `approve` and `cancel` prints exactly one JSON object on stdout and never prompts. Additive schemas: `gator-override-status-v1`, `gator-override-approve-v1`, `gator-override-cancel-v1` (see `scripts-cross-cutting.md`).
- **One refusal sequence.** `_approval_refusal()` is the only approvability decision, shared by the human and JSON `approve` paths and by `status --json` (`can_approve`, `approve_refusal`). Closed codes, in order: `no-block`, `malformed`, `block-changed`, `findings-changed` (or `unavailable`), `tree-changed`, `expired`, `legacy`, `nothing-approvable`, `too-recent` (`retry_after_seconds`). JSON approve adds `invalid-input` (blank name/reason, or over the `TRAILER_MAX` bounds 80/200, so a stored approval never differs from its trailer) and `write-failed`. A `precommit_override` environment error is `unavailable` (status: `state`; approve/cancel: `refusal`), exit 1. Human output is unchanged.
- **Revision.** `_snapshot()` reads block and approval once. `revision` = first 16 hex of sha256 over `[block_part, approval_part]` (compact JSON). A readable block contributes `[block_id, index_tree, [[rule, resolution, message]…]]` (recorded order, never `updated_at`, so an unchanged retry keeps it). A readable approval contributes its `approval_id`. An unreadable record contributes `["malformed", sha256(raw bytes)]`, and an absent one `null`. It is `None` when nothing is recorded, or when a record exists but its bytes cannot be read (`unreadable`: fail safe, nothing can match it).
- **Guards.** `--expect-block` / `--expect-revision` on `approve` and `cancel` are checked against the same snapshot the action uses (`_guard_refusal()`). `approve` builds the approval from that checked `block` object, so a block rewritten after the check never adds unseen rules to the approval. `cancel` with guards removes nothing on a mismatch. Without the flags both behave exactly as before.
- **Status record.** `state`: `none` | `blocked` | `approved` | `stale` | `expired` | `malformed` | `legacy` (`unavailable` on error). `approved` only when `inspect()` is `valid` and every external finding is covered. Fields: `revision`, `malformed` (list), `block` (id, times, `age_seconds`, `tree_matches`, `files`), `findings` (`rule`, `resolution` normalized to the three #75 values; a legacy value is `fix-required` + `legacy: true`; `message`; `covered`), `approval` (`inspect()` state/detail and, when present, id, approver, time and rules; never the reason), `approvable_rules`, `covered_rules` / `uncovered_external_rules` (from `precommit_override.approval_coverage()`), `can_approve` (no refusal AND an uncovered external rule), `approve_wait_seconds`, `min_approval_delay_seconds`, `architect_default` (`git config user.name` or null).
! The Dashboard is only a consumer. Approval stays Architect-only, `can_approve` is advisory display, and the write path re-runs the whole sequence. An orphan approval with no block reports `state: none` with a non-null `revision`.
! Byte-identical with the Enterprise bundled copy (`TestByteIdentityAcrossThreeCopies`).

### approval_coverage(approval, rule_resolutions)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
The ONE coverage definition (#76): the set of rules a valid approval removes, i.e. those in `approved_rules` whose resolution `is_approvable()`. Pure; the caller decides validity (`inspect()` → `valid`) first and, like the hook, does not compare block IDs.
<- `apply_approval()` (hook), `gator-approve.py` `status --json` (`covered_rules` / `uncovered_external_rules`)
! A valid approval is not complete coverage: after the supersede case (A approved, same-tree block now A+B) B is uncovered. Consumers must use this helper, never `approval.state == "valid"`, to decide what still needs approval.

### apply_approval(sdir, tree, failures, resolutions=None) / render_block_report(header, failures, warnings, resolutions, notes, block, info_lines=(), attention=())
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
The ONE approval decision and the ONE blocked-attempt report, shared by every validate path — strict mode in both pre-commit copies and the Enterprise `evidence_only` lint path — so they cannot diverge. `apply_approval` clears a stale handoff, retires an expired/mismatch/malformed/premature approval (note), removes only failures whose rule the valid approval names AND that classify `external-approval` under the attempt's map (never a fix-required rule; computed by `approval_coverage()`), writes the handoff when nothing remains, and returns `(remaining, handoff, notes)`; it never deletes a valid approval. `render_block_report` returns failures tagged `[fix-required]` / `[external-approval]` / `[pause]`, the `attention` findings tagged `[warning]` ("no approval command"), warnings, notes, info lines, a three-line Resolution summary, the Architect STOP box (only when an external-approval failure exists), the PAUSE box (only when the pause failure exists; it names the acknowledgement and skip fields and has no approval command), and the Block ID pointer.
<- `gator-pre-commit.phase_validate()` (template + bundled strict path), bundled `evidence_only` branch
! New validate paths must call these rather than re-implementing approval application or the report.

### describe(block, approval, tree, now=None)
File: `src/gator_command/templates/gator-starter/scripts/precommit_override.py`
Shared status text: block id, age, expiry, whether the current tree still matches, each failure with its resolution, files, and any approval.
<- `gator-approve.py`

### _walk_parent_pids(start_pid=None, max_depth=10) / _get_process_info(pid) / _get_process_info_windows(pid) / _get_process_info_windows_native(pid) / _get_process_info_windows_powershell(pid) / _filetime_to_cim_iso(filetime)
File: `src/gator_command/templates/gator-starter/scripts/precommit_session.py`
Commit-time session attribution: walk this process's parent chain as `(pid, started_at)` pairs and match them against registry `owner_pid` / `owner_pid_started_at` (`_pid_start_times_match`). Returns `[]` when the first hop fails; attribution then degrades to the single-session / no-session paths.
- **Windows:** `_get_process_info_windows` tries `_get_process_info_windows_native` first (kernel32 `CreateToolhelp32Snapshot` for the parent PID, `GetProcessTimes` for the start time; milliseconds, no child process). It falls back to `_get_process_info_windows_powershell` (`Get-CimInstance`, 10 s limit) only when the native path cannot find the process or read its start time, so a hop is never worse than the PowerShell-only behaviour. A PowerShell start time is used with a native parent PID only when both agree on the parent.
- **Unix:** `ps -o ppid=,lstart=` (5 s limit).
<- `_pick_session_for_commit()` attribution path
-> `_get_process_info()` per hop
! **Start-time strings are compared exactly** against what `gator-session-start.py` `_get_owner_pid_started_at()` recorded with PowerShell `CreationDate.ToUniversalTime().ToString('o')`. `_filetime_to_cim_iso` reproduces that byte-for-byte: CIM carries whole microseconds, so FILETIME is truncated to microseconds and printed with 7 fractional digits ending in 0 (verified against CIM on 7 live processes, 2026-10-09; pinned by `TestWindowsNativeProcessInfo`). Printing full 100 ns precision would silently break attribution. Changing either side's format requires changing both.
! Why native: the PowerShell cold start could exceed its 10 s limit on a busy Windows machine, so the walk returned `[]` (the recurring Windows CI flake in `TestPidWalker`, and silent attribution loss for users on slow machines).
! Byte-identical with the Enterprise bundled copy (`TestByteIdentityAcrossThreeCopies`).

## Testing Notes

`tests/test_precommit_override.py` drives REAL git commits in throwaway temp repos whose `pre-commit` / `commit-msg` / `post-commit` hooks are generated `sh` scripts calling the template (or Enterprise bundled) `gator-pre-commit.py`. Two constraints:

- Hook scripts must be written with LF line endings (`sh` on Windows rejects CRLF), using `open(path, "w", newline="\n")` — not `Path.write_text(newline=...)`, which requires Python 3.10+.
- Test code and fixtures must run on Python 3.9, the lowest version in the CI matrix (`source-ci` fast lanes on Ubuntu and Windows). A 3.10+ API in a fixture errors every test in the file on those lanes.

Approval in these tests runs `gator-approve.py approve` only inside the temp repos — never against this repository's own blocks. The charter escape hatch (`TestCharterEscapeHatch`, both copies) and the #35 second-block headline exercise the envelope in strict mode; the supersede, expiry, retry-safety and trailer-injection tests run through the bundled copy with `GATOR_HOOK_MODE=evidence_only` and a staged SQL-001 finding. Strict-mode warning tests stage `migrate.txt`, because `.txt` is charter-exempt while `.sql` is code. Legacy-migration fixtures write pre-#75 `block.json` / `approval.json` / `handoff.json` records by hand.

## Delivery (where these scripts run)

| Runtime | Source | Reaches a repo via | Pin |
|---|---|---|---|
| Wheel runtime (canonical) | `src/gator_command/templates/gator-starter/scripts/` | Not copied; `gator-hook.py` runs the wheel's template scripts and siblings resolve from the same dir | `pyproject.toml` package-data `templates/**/*` |
| Enterprise bundled | `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/` | `repo_init._install_bundled_scripts()` copies every `*.py` to `.gator/scripts/` | byte-identity + install self-sufficiency tests (see [`scripts-enterprise-cli.md`](scripts-enterprise-cli.md)) |
| Repo-resident `.gator/.includes/scripts/` | Retired (runtime-split Phase 4) | Not shipped | — |

When a sibling module is added or its semantics change, change the Enterprise bundled copy in the same commit. `precommit_policy.py` (#75) is such a sibling: `repo_init._install_bundled_scripts()` copies it with every other `*.py`.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) — trailer compatibility, shipped-copy synchronization
-> [Session Boot and Hook Dispatch](scripts-repo-lifecycle.md) — `gator-hook.py` routes `override` / `approve`
-> [Session Archaeology](scripts-session-archaeology.md) — snippet emission in cleanup
