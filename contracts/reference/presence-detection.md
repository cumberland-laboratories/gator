---
contract-id: presence-detection
kind: reference
owners: base Gator, Enterprise capability
tested-by: contracts/compatibility/test_enterprise_marker.py
---

# Presence Detection

## The two directions

The monorepo ships both halves in one wheel. Runtime behavior still
depends on two separate presence signals:

1. **Base Gator on a repo** — canonical check: `.gator/` is a directory.
2. **Enterprise configured on a repo** — canonical check: `.gator/enterprise.json` exists.

Both signals are file-system facts. Neither depends on installed
packages, environment variables, or shell state.

## Base Gator presence

**Signal**: `(repo_root / ".gator").is_dir()`.

**Canonical readers**:
- `find_repo_root` in `gator-enforce.py:24` — walks up from cwd until
  it finds `.gator/`.
- `find_gator_root` in `gatorize.py:100` — same pattern for install-time
  checks.
- Dashboard fleet-add auto-discovery uses the same check.

**Historical note**: An earlier "command-post" concept had its own
`_HAS_COMMAND_POST` toggle. That was retired in v2.0.0 (see
`gator-command/artifacts/2026-06-23-retiring-command-post-architecture-cut-plan.md`).
No component in `main` uses that flag today.

## Enterprise configuration presence

**Signal**: Enterprise is considered *active* on a repo iff
`.gator/enterprise.json` exists AND parses as a JSON object AND
carries `enabled: true` (literal, not truthy). Presence of the file
alone is not sufficient — `enabled: false` in the marker is the
temporary-disable case; malformed JSON or a non-object root
(e.g. `[]`, `42`) MUST fail closed as inactive.

**Canonical production reader**:
`gator_core.is_enterprise_active(gator_dir)` — landed Phase
4b-substrate (2026-08-01). Every Enterprise gating call site MUST
use this helper rather than reimplement the check; divergence between
call sites is the exact regression the invariant defends against.
See `scripts-core-library.md` for the function-level charter entry
and `tests/test_gator_core.py::TestIsEnterpriseActive` for the pinning
tests. The reference implementation
`_is_enterprise_active` in
`contracts/compatibility/test_enterprise_marker.py` and the production
helper MUST stay byte-behaviorally identical — if either changes,
both should be updated together.

**Consumers (planned)**: hook and CLI paths in the `gator enterprise`
subcommand group (Phase 4c) and any Enterprise-side session-block /
transcript-capture / Audit-view / ledger-enrichment code paths. Per
amended Decision B (2026-08-01), base-Gator snippet emission does
NOT consult the marker — base behavior is unconditional; the marker
gates the *additive* Enterprise layer only.

## Reciprocal contract obligations

**Base Gator MUST**:
- Not depend on `.gator/enterprise.json` for any base-path behavior.
- Function identically whether the marker is present or absent.
- Not emit session snippets differently based on the marker.

**Enterprise capability MUST**:
- Read the marker via `gator_core.is_enterprise_active(gator_dir)` — the single canonical helper. No re-implementation permitted.
- Gate every Enterprise-side side effect on the helper returning True.
- Fail closed: unreadable, malformed, non-object, or `enabled != true` → treat as absent.
- Never modify base Gator's `.gator/config.json` `enforcement_level`
  without an explicit operator action.

## Separation from Enterprise-server connection state

`~/.gator/enterprise/` (user-scoped, per-machine) already holds
Enterprise-server connection state — `hook-policy.json`, cached
policies. That is a **machine-scoped** surface owned by
`gator enterprise setup`. `.gator/enterprise.json` (repo-scoped) is a
different marker: it records that this specific repo has been opted
into Enterprise integration.

- `~/.gator/enterprise/…` — this machine has an Enterprise account.
- `.gator/enterprise.json` — this repo participates in Enterprise
  evidence flow.

Both can coexist independently. A machine with an Enterprise account
can still have repos with no `.gator/enterprise.json`.
