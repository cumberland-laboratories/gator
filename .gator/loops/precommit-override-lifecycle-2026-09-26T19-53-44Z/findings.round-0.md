# Review: Retry-Safe Pre-Commit Override Approval

## Executive Summary

- The tree-bound, per-worktree state directory is the right core design. It solves the #34 scope problem and avoids Dashboard/staging exposure by construction.
- The plan must preserve an approval when a non-approvable secondary failure remains. As written, refreshing `block.json` after removing an approved rule can change the failure set and therefore the block ID, which risks orphaning the still-valid approval.
- `gator hook override status|cancel|approve` is dispatched by `gator-hook.py`, not parsed by `cli.py`. The implementation needs an explicit dispatcher route and compatibility tests.
- Add caller-root resolution and tests for approval/status/cancel from a governed subdirectory and linked worktree. The current dispatcher deliberately leaves those user-driven commands at their caller cwd.

## Verdict

REVISE

## Findings

### Finding 1: Define the durable authorization identity across secondary failures

**Severity**: High

**Issue**: In the stated validate sequence, a valid approval removes its
approvable failures, but a remaining `fix-required` failure causes
`block.json` to be refreshed. The plan says the block ID remains stable only
when both tree *and failure set* are unchanged. A charter + invalid
change-type attempt therefore has a changed failure set after approval and can
replace the block ID / invalidate the approval before the Architect fixes the
draft. That contradicts the required #35 lifecycle and the plan's own Sketch
1 test.

**Required revision**: Specify one invariant explicitly: for an unchanged
index tree, a prior approval remains associated with the pending attempt while
only unrelated or fix-required failures change. For example, retain a stable
attempt/authorization ID and record current failures separately, or give the
approval its own immutable request snapshot and validate its approved-rule
subset against the current failures without overwriting that snapshot. Define
which event (tree change, expiry, cancellation, or newly introduced
approvable rule) actually supersedes approval, and add tests for each.

### Finding 2: Route nested override commands through `gator-hook.py`

**Severity**: High

**Issue**: `src/gator_command/cli.py` has one generic `hook` command that
passes its arguments to `gator-hook.py`; it does not own nested hook parsing.
`gator-hook.py` currently maps only the hook name `approve` to
`gator-approve.py`. Adding a route to `cli.py` alone will not make
`gator hook override status` work.

**Required revision**: Name the dispatcher change: add an `override` route in
`HOOK_MAP` (or an equally explicit translation in `gator-hook.py`) that
forwards `status|cancel|approve` to `gator-approve.py`, while retaining
`gator hook approve` as the compatibility alias. Add dispatcher tests for
argv forwarding, unknown subcommands, and the existing non-blocking exit-code
contract. Do not list `cli.py` as changed unless a real top-level help or
validation change is necessary.

### Finding 3: Make worktree-root discovery a concrete responsibility

**Severity**: Medium

**Issue**: The state location correctly uses `git rev-parse --git-path`, but
`gator hook approve` deliberately preserves the caller cwd. The rewritten
approval script must itself obtain the correct Git worktree top-level before
calling `state_dir`; the present `find_gator_dir()` only finds `.gator/`.

**Required revision**: Add a `resolve_repo_root()` / `git_path()` seam to the
shared module or approval script, define its error handling, and test
approve/status/cancel from a governed subdirectory and a linked worktree.
This preserves the existing dispatcher contract while making the per-worktree
state claim real.
