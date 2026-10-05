# Implementation Plan: Coding Loop with Diff-Aware Implementation Review (#41) — Revision 1

## Executive Summary

- **What.** Add an optional coding mode, `session.mode = "coding"`, started only as a guarded successor of an approved planning loop. The CLI captures the raw Git facts. Implementation reviews and approval bind to the exact raw staged-tree OID. The Draftor then makes one ordinary commit.
- **Key decisions (revised).**
  - After approval, status resolves to one of three states. **Committed** means `HEAD^{tree}` equals the reviewed tree. **Pending** means the reviewed tree is still staged, unchanged. **Stale** is anything else.
  - A new Architect-only `reopen` moves `implementation_approved` to `implementation_revision`.
  - The snapshot contract is `snapshot(worktree_root, base_head)`, with raw facts only and no path filtering.
- **Main risk.** Hook-managed `.gator/` files changing the tree during commit. Mitigation: the Draftor stages the hook-produced files before submitting (the raw tree is authoritative).
- **Verification.** Six modules. The full planning suite runs unchanged. New end-to-end tests cover the commit handoff, reopen, and successor-validation failures.

## Response to Findings

1. **Post-approval commit vs. stale (High): adopted.** See Change 4, "Approval resolution". A normal commit whose tree equals `reviewed_tree` shows as **Committed** (successful handoff), with the commit OID displayed. STALE applies only to an uncommitted candidate whose staged tree differs, or a new commit whose tree differs. A detached HEAD is handled by the same tree comparison and is reported as "detached".
2. **No re-review path (High): adopted.** There is a new Architect-only `reopen` transition from `implementation_approved` to `implementation_revision` (Change 1/4). `extend` is not reused and stays limited to `max_rounds_exceeded`.
3. **Snapshot interface (Medium): adopted.** It is now one typed contract, `snapshot(worktree_root, base_head)`, with a command and failure behavior specified for each field (Change 2).
4. **Hook-managed paths (Medium): adopted, using the reviewer's preferred option.** There is no filtering. The raw staged-tree OID and raw changed paths are authoritative everywhere: the artifact, the display, the approval, and the stale check. The protocol requires the Draftor to stage the final `commit_draft.md` and charters *before* `submit-implementation`. The commit-time hook rewrites (`status.json`, the draft reset) happen after the commit. Resolution therefore compares `HEAD^{tree}` with the reviewed tree. If a hook alters tracked content inside the commit itself, the result is STALE and gets an explicit "hook changed committed tree" reason. That is a known, tested limitation, not a silent pass.
5. **Successor validation (Medium): adopted.** See Change 1, "Start". It validates the canonical loop ID and the source mode and stage, reads under the source session lock, copies then hashes the plan before publishing the new session, and fails atomically. Rejection tests are listed under Testing.

## Summary

Add a coding mode discriminator without changing planning semantics. `loop/gitsnap.py` captures raw Git facts against the captured base. Submissions and reviews bind to the raw staged-tree OID. Approval resolution distinguishes **Committed**, **Pending** and **Stale**, and an Architect `reopen` returns a changed candidate to review. The Dashboard shows the bindings and the final handoff. There is no commit wrapper, no hook bypass, and no per-round commits.

## Approach

Decisions on the sketch's questions (unchanged from round 0, with clarified rule 4):
1. Unstaged residue is **disclosed, not blocking**. Only the staged tree is the candidate.
2. The plan is referenced by both an immutable `approved-plan.md` copy and `{source_loop_id, plan_sha256}`.
3. The base is captured at coding-loop start (`base_head`). A branch move is displayed when `current_head != base_head`.
4. **Approval resolution** (from Finding 1): the raw tree is compared with `HEAD^{tree}` and with the staged tree, never filtered.
5. A coding loop starts only as a guarded successor: `start --mode coding --from-loop <id>`.

## Changes

### 1. Mode, schema, start, and reopen
- Files: `loop/session.py`, `loop/state_machine.py`, `loop/host.py`, `loop/submit.py`, `loop/cli.py`
- What:
  - `create_session(..., mode="planning")`.
  - The coding block is `coding: {source_loop_id, plan_sha256, base_head, generations: [], approval: null}`.
  - Stages: `implementation_drafting`, `implementation_review`, `implementation_revision` (active, Draftor/Reviewer/Draftor), and the terminal `implementation_approved`. `validate_action()` dispatches on `mode` (default `planning`).
  - **Start (Finding 5):** `start_loop(..., mode="coding", from_loop=ID)`:
    1. Reject an ID that fails the `_LOOP_ID_RE` / no-separator check.
    2. Resolve `.gator/loops/<ID>`.
    3. Under the source `with_session_lock` read callback (no write), require `mode == "planning"` and `stage == "plan_approved"`.
    4. Read `plan.current.md`, which must exist and be non-empty.
    5. Create the new loop dir under `start.lock`.
    6. Write `approved-plan.md`, compute its SHA-256, and re-read it to confirm the digest.
    7. Snapshot `base_head`, which must be ok.
    8. Only then write `session.json` and the tokens.

    Any failure removes the partial dir and raises one clear error.
  - **Reopen (Finding 2):** an Architect-only `handle_reopen(token, message)`. It is valid only from `implementation_approved`. It sets `implementation_revision` for the Draftor with a fresh deadline, keeps the round counter (a new submission makes round + 1), and records `approval.invalidated_at`. It appends an Architect `reopen` turn and emits a `loop_reopened` event. CLI: `gator loop reopen --token <architect> --message "..."`.

### 2. Git snapshot helper (Finding 3)
- File: new `loop/gitsnap.py`
- Contract: `snapshot(worktree_root, base_head) -> dict`:

| Field | Command | Failure |
|---|---|---|
| `worktree_root` | `git rev-parse --show-toplevel` | `not_a_repo` |
| `current_head` | `git rev-parse --verify HEAD` | `unborn` |
| `detached` | `git symbolic-ref -q HEAD` (exit code) | — |
| `head_tree` | `git rev-parse HEAD^{tree}` | `unborn` |
| `staged_tree` | `git write-tree` | `conflict` (unmerged index) |
| `changed_paths` | `git diff --cached --name-status <base_head>` | `bad_base` |
| `unstaged_paths` | `git diff --name-only` + untracked from `git status --porcelain` | — |

- Returns `{ok: True, ...}` or `{ok: False, error: <code>}`. Git missing gives `git_unavailable`. One retry on an index lock, then `git_busy`. These are raw facts; the persisted generation stores exactly the returned dict.
- Linked worktrees **are** supported, because `--show-toplevel` and the per-worktree index are used. Unborn, conflict and bare repos are explicitly rejected (tested).

### 3. Implementation submission
- Files: `submit.py` (`handle_submit_implementation`), `cli.py` (`submit-implementation`)
- What:
  - Required headings: Executive Summary, Implementation Summary, Charter Updates, Verification, Commit State.
  - `snapshot(root, base_head)` must return `ok`, and `staged_tree` must differ from the tree of `base_head` (something is staged).
  - The CLI writes the Commit State block from the raw snapshot, replacing the author's section, to `implementation.round-N.md` and `implementation.current.md`.
  - It appends the generation and emits `implementation_submitted`.

### 4. Review, staleness, and approval resolution (Finding 1)
- Files: `submit.py`, `cli.py`, plus a new pure `resolve_approval(approval, snap)`
- What:
  - **Review:** a fresh snapshot runs before a review is accepted. A mismatch with the latest generation's `staged_tree` or `current_head` rejects the review with "candidate changed since submission". Findings record `reviewed_tree` / `reviewed_head`. APPROVE sets `implementation_approved` and `approval: {tree, head, ts}`.
  - **Resolution** (used by `status`, the Dashboard and tests):
    - **Committed:** `head_tree == approval.tree` and `current_head != approval.head`. Shows the commit OID: "handoff complete".
    - **Pending:** `current_head == approval.head` and `staged_tree == approval.tree`. Shows "return to the Draftor session for one normal commit".
    - **Stale:** anything else, with a reason: `staged_tree_changed`, `head_moved_tree_differs` (including "hook changed committed tree"), or `detached_mismatch`.
    - **Unknown:** the snapshot is not ok, so the error is shown and never treated as approved.
  - Stale or Unknown shows the Architect's `reopen` affordance.

### 5. Dashboard
- Files: `gator-dashboard.py`, `dashboard/views/loop.js`
- What:
  - The status allowlist gains `mode` plus the `coding` facts (no tokens).
  - A new Architect-only GET `/loops/<id>/snapshot` (`no-store`, through the M4-style architect resolver) returns `resolve_approval()` plus the raw facts.
  - A POST `/reopen` runs through `_LOOP_ACTIONS`.
  - UI: the coding header shows the round, base/current/reviewed/staged short OIDs, the changed-path summary, the unstaged warning, the verdict and a link to the approved plan. The resolution banner uses text plus an icon: **✓ Committed**, **● Pending commit**, **⚠ Stale (reason)**, **? Unknown (error)**. The Reopen control appears only when Stale or Unknown. All of this uses incremental regions, so identical polls cause no mutation.

### 6. Protocol and docs
- Files: the protocol pair, the `loop-artifact-formats.md` pair (implementation template), `/loop-join`
- What: the coding steps, "stage hook-produced files before submitting", the commit handoff, and reopen.

## Dependencies and Ordering

2 → 1 (start needs `base_head`) → 3 → 4 → 5 → 6.

## Assumptions, Risks, and Required Architect Decisions

- **Non-blocking:** residue is disclosed, not blocking. This is reversible.
- **Non-blocking:** reopen keeps the round counter, and coding-mode `max_rounds_exceeded` stays extendable via the existing #39 `extend`.
- **Risk:** hooks that modify tracked files *inside* the commit make it STALE. The reason is explicit, and the Architect reopens.
- **Risk:** Windows index locks are handled by one retry, then `git_busy`.

## Testing

- **Planning regression:** `tests/test_loop.py` runs unchanged, and planning `validate_action` is unaffected by mode.
- **gitsnap**, in temp repos: clean, staged, unstaged/untracked, unborn, conflict, linked worktree, bad base, detached HEAD, Git missing.
- **Start rejection (Finding 5):** a non-approved source, a coding-mode source, a missing or empty plan, an invalid ID, a digest mismatch (a corrupted copy), and a failure partway through leaving no partial dir.
- **End to end:**
  1. Clean approval, then the ordinary commit shows **Committed**.
  2. A tree changed after submission makes the review rejected.
  3. An uncommitted change after approval shows **Stale**, then `reopen`, a resubmission, review, and approval (Finding 2).
  4. Multi-round revision.
  5. Restart recovery from the persisted generations.
  6. A hook-modified commit shows Stale with the reason.
- **Dashboard:** the snapshot and reopen endpoints (authority, `no-store`), plus Playwright tests for the banners, the reopen visibility and zero-mutation polls.

## Charter Impact

`scripts-loop.md` (mode, stages, gitsnap contract, reopen, TRIPWIRE "raw staged tree is authority"), `scripts-dashboard.md`, `scripts-dashboard-ui.md`, and the protocol cross-reference.
