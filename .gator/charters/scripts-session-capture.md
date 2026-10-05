# Charter: Vendor Session Capture

**Covers**: `src/gator_command/templates/gator-starter/scripts/gator-session-start.py`, `src/gator_command/templates/gator-starter/scripts/gator-session-open.py`

## Owns

- Vendor SessionStart payload normalization and active-session registry writes.
- Silent session-open hook self-heal and local policy-staleness nudge.
- Nonblocking behavior across Claude Code, Codex CLI, and Gemini CLI payload differences.

## Does Not Own

- Hook command installation; see [`scripts-installer.md`](scripts-installer.md) and [`scripts-repo-update.md`](scripts-repo-update.md).
- Hook runtime dispatch; see [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md).
- Aggregation of committed snippets; see [`scripts-session-archaeology.md`](scripts-session-archaeology.md).

---

### detect_vendor() / extract_vendor_session_id()
File: src/gator_command/templates/gator-starter/scripts/gator-session-start.py
Normalize vendor identity and stable session identity from vendor-specific payload shapes.
<- vendor SessionStart hook
! Unknown or incomplete payloads degrade to explicit unknown identity without raising.

### extract_model() / extract_transcript_path() / extract_cwd() / extract_started_at()
File: src/gator_command/templates/gator-starter/scripts/gator-session-start.py
Extract optional session metadata while preserving absence as absence.
<- `build_session_file()`
! Do not invent paths or timestamps from the hook process when the vendor supplied a different value.

### build_session_file(payload)
File: src/gator_command/templates/gator-starter/scripts/gator-session-start.py
Build the normalized active-session record, including process identity when available.
<- session-start `main()`
-> vendor extractors and owner-process probes
! Process identity is `(pid, process-started-at)`, not PID alone; PIDs are reusable.

### _filter_stale(entries) / write_session_file(gator_dir, entry)
File: src/gator_command/templates/gator-starter/scripts/gator-session-start.py
Remove provably stale process records and atomically update the active-session registry.
Filesystem: `.gator/sessions/_active/` state (RW)
<- session-start `main()`
! Preserve concurrent live sessions. One vendor session must not overwrite a different active session.
! Uncertain liveness is retained rather than deleting potentially active evidence.

### find_gator_dir()
File: src/gator_command/templates/gator-starter/scripts/gator-session-open.py
Walk to a `.gator/` directory only when it belongs to a Git worktree.
<- session-open `main()`
! Machine-local `~/.gator` is not a governed repository.

### main() [gator-session-open.py]
File: src/gator_command/templates/gator-starter/scripts/gator-session-open.py
Resolve v2, v1, or wheel-local runtime helpers, self-heal Git hooks, log degraded status, and emit an optional stderr policy nudge.
<- vendor SessionStart hook through `gator hook session-open`
-> `gator-init.ensure_git_hooks()`, diagnostics, policy nudge
! Always exit zero and never write stdout. Vendors may interpret stdout as agent context.
! Invalid/missing layout or helper modules degrade silently; diagnostic logging is best-effort.

### main() [gator-session-start.py]
File: src/gator_command/templates/gator-starter/scripts/gator-session-start.py
Read one JSON payload from stdin and persist normalized active-session identity.
<- vendor SessionStart hook through `gator hook session-start`
-> `build_session_file()`, `write_session_file()`
! Hook errors do not block tool startup; diagnostics go to stderr or bounded logs, never structured stdout unless the hook contract requires it.

## Before Changing This Module

- Test all vendor payload shapes, missing fields, reused PIDs, and concurrent sessions.
- Preserve zero-exit/nonblocking behavior and session-open's no-stdout contract.
- Check every byte-identity-governed copy, including Enterprise bundled scripts.
- Run session-hook, multi-session, dispatcher, and template-sync tests.

## Connections

-> [Session Boot](scripts-repo-lifecycle.md) - runtime dispatch and correct Git root
-> [Installer](scripts-installer.md) - vendor settings installation
-> [Repo Update](scripts-repo-update.md) - hook repair and template overlay
-> [Session Archaeology](scripts-session-archaeology.md) - downstream evidence grouping
-> [Enterprise CLI](scripts-enterprise-cli.md) - bundled-copy synchronization
