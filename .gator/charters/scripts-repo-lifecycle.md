# Charter: Session Boot and Hook Dispatch

**Covers**: `src/gator_command/scripts/gator-init.py`, `src/gator_command/scripts/gator-hook.py`, `src/gator_command/templates/gator-starter/scripts/gator-init.py`

## Owns

- The standardized `gator init` boot display and machine-readable status.
- Session-opening instructions, hook health checks, and dashboard auto-registration.
- Runtime-aware dispatch for Git and vendor session hooks.

## Does Not Own

- Template overlay, layout migration, policy sync, or hook installation; see [`scripts-repo-update.md`](scripts-repo-update.md).
- Core runtime/registry helpers; see [`scripts-core-library.md`](scripts-core-library.md).
- Vendor payload capture implementation; see [`scripts-session-capture.md`](scripts-session-capture.md).
- Charter analysis or pulse generation.

---

### count_constitution_rules() / count_charters() / count_working_set() / count_field_guides()
File: src/gator_command/scripts/gator-init.py
Compute compact boot-status counts from the resolved Gator layout.
Filesystem: `.gator/` governance surfaces (R)
<- text and JSON boot output
-> layout resolver
! Counts are status hints, not proof that content was read or semantically valid.

### ensure_git_hooks(repo_root, paths)
File: src/gator_command/scripts/gator-init.py
Probe managed and legacy hook locations and request repair when configuration is stale.
<- `main()`
-> repo updater hook helpers
! Session opening remains nonblocking. An unresolvable hook launcher is reported as degraded, not falsely healthy.

### session_opening_directive(repo_root, paths)
File: src/gator_command/scripts/gator-init.py
Return the exact resolved constitution path plus mission/roadmap/inbox next actions.
<- `print_boot_sequence()`
! The directive follows the tagline and precedes the final marker so models do not interpret the banner as completion.

### print_boot_sequence() / print_json()
File: src/gator_command/scripts/gator-init.py
Render equivalent human and machine status for governance, hooks, and registry membership.
<- `main()`
-> counters, hook status, constitution drift
! Constitution drift is warning-only and best-effort; failure to compare templates never blocks session opening.

### main()
File: src/gator_command/scripts/gator-init.py
Resolve the governed repo, self-check hooks, register the repo in the dashboard registry, and emit boot output.
<- `gator init`, optional vendor hook mode
-> `gator_layout`, `gator_core`, update helpers
! Outside a governed repository, hook mode returns silently and normal mode prints the not-found guidance.
! Registry failure does not prevent the boot display.

### _resolve_repo_root(cwd, hook_name)
File: src/gator_command/scripts/gator-hook.py
Resolve the Git top level for `session-open` and `session-start`; preserve the caller directory for commit hooks.
<- hook dispatcher `main()`
-> `git -C <cwd> rev-parse --show-toplevel`
! Git failure, empty output, or subprocess failure returns the original cwd.
! A nested ungoverned Git repository inside a governed parent resolves to the nested root and remains ungoverned.

### plan_dispatch(hook_name, repo_root, decision, wheel_dir=None)
File: src/gator_command/scripts/gator-hook.py
Choose the repo or wheel script and argv for one hook without executing it.
<- dispatcher `main()`
-> runtime decision, hook-name mapping
! Commit hooks keep established warning/fail-open behavior. Session hooks remain nonblocking.

### main(argv=None)
File: src/gator_command/scripts/gator-hook.py
Resolve the correct repo, choose the governed runtime, and invoke the selected hook from that repo root.
<- managed Git wrappers and vendor settings
-> `_resolve_repo_root()`, `resolve_governed_runtime()`, `plan_dispatch()`
! Child cwd and governance lookup use the same resolved repo root.
! Do not broaden Git-root resolution to commit hooks without a separate compatibility decision.

## Before Changing This Module

- Test repo root, governed subdirectory, linked worktree, outside Git, and nested ungoverned Git cases.
- Preserve nonblocking session-hook behavior and existing commit-hook semantics.
- Keep package and starter-template `gator-init.py` copies synchronized where required.
- Run init, hook, installer, and session-hook focused tests.

## Connections

-> [Repo Update](scripts-repo-update.md) - hook repair and shipped content
-> [Core Library](scripts-core-library.md) - runtime, layout, and registry helpers
-> [Session Capture](scripts-session-capture.md) - vendor payload normalization and nonblocking hook bodies
-> [Cross-Cutting](scripts-cross-cutting.md) - runtime and hook contracts
