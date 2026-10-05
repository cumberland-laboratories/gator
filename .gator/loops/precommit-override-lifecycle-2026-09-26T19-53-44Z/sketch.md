# Implementation Sketch: Retry-Safe Pre-Commit Override Approval (#34, #35)

## Purpose

Repair the pre-commit approval path as one small, explicit state machine.
An Architect must approve one exact staged Git index, and that approval must
remain usable until that index commits or becomes invalid. This resolves both
the integrity problems in #34 and the user-visible dead end in #35.

## Current failure chain

`phase_validate()` calls `check_override()` before it has evaluated all hard
rules and Layer 1 lint. A matching approval is deleted immediately. The retry
can then fail for another reason, with no remaining request. Further, a
request is created only for three charter rules, so `gator hook approve` calls
every other block "No pending override request" even when a precise diagnosis
is possible.

## Proposed direction

### 1. Shared, versioned pending-block state

Introduce a small shared module used by `gator-pre-commit.py` and
`gator-approve.py`. It owns JSON validation, atomic read/write/retirement, and
the state vocabulary; do not duplicate JSON interpretation between scripts.

The request records a schema version, block ID, creation/expiry time, complete
`git write-tree` OID, all failed rules, and the resolution class for each rule:

- `approvable` — the Architect may authorize this exact index.
- `lint-allow` — either migrate into the common approval envelope, or return a
  direct and truthful lint-resolution instruction.
- `fix-required` — malformed frontmatter and similar correctness failures;
  never silently approvable.

The display list of files may be truncated, but the authorization binding must
use the complete index tree. An approval copies the block ID, tree OID,
expiry, approved-by identity, and a bounded, single-line reason. Malformed,
legacy, expired, or mismatched state fails closed with an actionable message.

### 2. Validate first; consume only after the commit lands

Restructure pre-commit in this order:

1. Capture the staged tree and evaluate every hard rule and lint finding.
2. Inspect a matching pending approval without deleting anything.
3. Apply only the authorization that is valid for this exact tree; produce a
   complete block record/output for unresolved failures.
4. On a clean validation result, write a handoff record for `commit-msg` that
   contains the durable trailer values, but retain retry state.
5. Let `commit-msg` append sanitized audit trailers without consuming state.
6. Let `post-commit` perform idempotent final cleanup of request, approval,
   handoff/meta, and obsolete transient state.

Thus a secondary failure, a commit-message failure, or a Git failure after
`commit-msg` preserves a valid approval for an unchanged retry. Any staged
add, deletion, rename, or content edit changes the tree OID and requires a
new approval. A new request supersedes incompatible older state atomically.

### 3. Make #35's resolution path explicit

Every blocked attempt should create or refresh inspectable pending-block state,
even when no rule is approvable. Hook output and `gator hook approve` must say
which unresolved rules are approvable, need lint resolution, or must be fixed.
Never report a generic missing request when a current block record exists.

Keep `gator hook approve` as the compatibility entry point. Opus should assess
whether `gator hook override status` and `cancel` are worth adding in this
slice; status/cancellation solve abandoned-request ambiguity, while approval
remains Architect-only. Choose and document a bounded expiry.

## Adjacent convergence work

- Synchronize the starter-template hook files and the Enterprise bundled
  `gator-pre-commit.py`; identify every byte-identity or packaging test before
  choosing module placement.
- Extend the canonical `ensure_repo_gitignore()` convergence list for all
  transient override files: request, approval, handoff/meta, legacy
  `.override`, and `commit_issues.md`. They must never be staged as governance
  work.
- Retire the documented direct `.gator/.override` bypass. A transitional
  detection/error with the approved command is safer than retaining it as an
  authorization path.
- Correct Dashboard content denial to cover the actual undotted request and
  approval filenames, as well as historical dotted aliases, for listing and
  every file-serving route.
- Make audit durable: emit sanitized, bounded trailers for override type,
  approver, block ID, and reason; update readers and user guidance together.

## Tests to plan

Focus integration tests on the whole lifecycle, with unit tests for state
parsing and tree comparison:

1. Charter block + invalid frontmatter (or HIGH lint) -> approval -> retry:
   the approval is retained and output identifies the remaining rule and its
   correct resolution path.
2. Unchanged staged tree approves and commits; every transient artifact is
   absent after post-commit.
3. Modifying, adding, deleting, renaming, or restaging any file invalidates
   approval clearly; an abandoned/expired/malformed pair cannot authorize.
4. A failure in `commit-msg` or Git after successful validation leaves the
   unchanged approval retryable.
5. A new block atomically supersedes stale incompatible request/approval
   state; explicit cancellation and expiry (if included) are diagnostic.
6. Approval reason/name cannot inject trailers; the resulting Git history and
   audit readers preserve the intended values.
7. Gitignore convergence, Dashboard list/file/raw denial, legacy-bypass
   retirement, and Enterprise bundled-copy synchronization are covered.

## Scope guard and design questions

Do not redesign charter policy, hook installation, or general Dashboard
transport. The key plan decision is whether to fold HIGH/CRITICAL lint into
the new common envelope now. A shared envelope gives one correct audit and
retry model; retaining `lint-allow.json` lowers migration scope but requires
equally clear diagnostics and must not leave an unscoped approval path.

Linked-worktree behavior deserves an explicit design check: state is stored
in a shared working-tree `.gator/` while each worktree has its own index. The
chosen state record must bind to the actual worktree/index, or the feature must
document and enforce its supported scope.
