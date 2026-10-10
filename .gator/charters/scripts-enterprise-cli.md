# Charter: Enterprise CLI

**Covers**: `enterprise/enterprise-cli/**`

## Owns

- The separately installed `gator_enterprise_cli` package and its command registry.
- Machine credentials, API client behavior, activation, repo provisioning, policy pull/drift, and operator reports.
- Claude, Codex, and Gemini transcript discovery and upload workflows.
- Enterprise-owned machine hook installation and bundled repo scripts.

## Does Not Own

- The base-wheel dispatcher; see [`scripts-enterprise.md`](scripts-enterprise.md).
- Server authorization, persistence, linkage, or reports; see [`scripts-enterprise-server.md`](scripts-enterprise-server.md).
- Base Gator's normal repo hooks and dashboard registry.

---

### main()
File: enterprise/enterprise-cli/gator_enterprise_cli/main.py
Registers command modules, constructs the authenticated client when required, and dispatches the selected handler.
<- base dispatcher, `gator-enterprise` entry point
-> `commands/*`, `EnterpriseClient`
! Registered verbs must remain synchronized with the base dispatcher's advertised set.

### EnterpriseClient / CliError
File: enterprise/enterprise-cli/gator_enterprise_cli/client.py
Owns authenticated HTTP requests, response decoding, and stable operator-facing failures.
<- command handlers
-> Enterprise API
! Never print or embed the API token in diagnostics.

### credentials_path() / write_credentials() / read_credentials() / remove_credentials()
File: enterprise/enterprise-cli/gator_enterprise_cli/credentials.py
Manage machine-scoped credentials under the user's Gator state directory.
Filesystem: machine credentials (RW)
<- authentication and activation commands
! Reads fail closed on malformed or unsafe state; POSIX writes preserve owner-only permissions.

### install_enterprise_vendor_hooks() / _merge_hooks()
File: enterprise/enterprise-cli/gator_enterprise_cli/vendor_hooks.py
Installs Gator-managed vendor session hooks while preserving unrelated user commands.
Filesystem: vendor settings files (RW)
<- activation
-> base `gator hook session-open` / `session-start`
! Prefer an absolute resolved Gator launcher because GUI-started tools may not inherit the pipx PATH.
! Re-running installation is idempotent and must not duplicate recognized old- or new-generation Gator hooks.

### activate.register() / activate.handle()
File: enterprise/enterprise-cli/gator_enterprise_cli/commands/activate.py
Activates a machine, installs global hooks, reports at-risk repo hooks, and synchronizes Enterprise state.
<- CLI dispatch
-> credentials, vendor hooks, Enterprise API
! `--force` repairs activation but does not silently rotate machine identity.
! Existing repository-local hooks remain visible as risk; global activation must not pretend they are governed by the new path.

### repo_init.register() / repo_init.handle()
File: enterprise/enterprise-cli/gator_enterprise_cli/commands/repo_init.py
Provisions a repository with Enterprise policy intent and bundled scripts.
Filesystem: governed repo `.gator/` state (RW)
<- CLI dispatch
! Default hook mode is `strict`. Persist the requested mode exactly.
! Transcript-first provisioning does not create or unignore `.gator/session-blocks/`.
! Bundled scripts governed by byte-identity tests must match their base/template counterparts.
! `bundled_scripts/` ships the full pre-commit runtime set (#34, #35): `gator-pre-commit.py` plus its siblings `precommit_override.py`, `precommit_lint.py`, `precommit_charter.py`, `precommit_session.py` (2026-10-09: Windows PID walk via native kernel32 with PowerShell fallback; see the `_walk_parent_pids` entry in [`scripts-precommit.md`](scripts-precommit.md)), and the Architect CLI `gator-approve.py`. `_install_bundled_scripts()` copies every `*.py` except `__init__.py`, so a new sibling ships automatically — but it must exist in the bundle, or the installed hook fails to import. Pins: `TestByteIdentityAcrossThreeCopies` (precommit_session, gator-session-start, precommit_override, gator-approve, precommit_lint) and `test_bundled_runtime_is_self_sufficient_after_install` in `tests/test_multi_session.py`. `gator-pre-commit.py` itself still has pre-existing drift (no change-type/significance enum gates); the #34/#35 override section is ported at the same anchors and exercised end to end by `TestEnterpriseBundledRuntime` in `tests/test_precommit_override.py`.
! Bundled `evidence_only` mode (`GATOR_HOOK_MODE`, the Enterprise default) keeps its minimal ceremony (no charter or commit_draft rules) but its HIGH/CRITICAL lint goes through the same tree-bound envelope: `write_block()` on a block, `precommit_override.apply_approval()` for an Architect approval of the exact staged change, `render_block_report()` for output, handoff → override trailers, and a deprecation note when `lint-allow.json` lists a still-blocking finding. Bundled `phase_cleanup()` calls `override_state.retire()` BEFORE its `evidence_only` early exit so the state is consumed in every mode. Pins: `TestEnterpriseEvidenceOnly` (block → approve → retry → retired; changed content needs a new approval; allowlist explained, not honored; clean commit passes).

### discover() / discover_claude_transcripts() / discover_codex_transcripts() / discover_gemini_transcripts()
File: enterprise/enterprise-cli/gator_enterprise_cli/transcripts_discovery.py
Discover vendor transcript files and normalize identity, timestamps, workspace hints, and session qualifiers.
Filesystem: vendor transcript stores (R)
<- transcript pull/upload commands
! Vendor-native identity remains part of deduplication. Gemini's session qualifier is required because one session ID may occur in multiple files.

### transcripts.register() / transcripts.handle()
File: enterprise/enterprise-cli/gator_enterprise_cli/commands/transcripts.py
Lists, uploads, retrieves, links, relinks, and batches transcript/commit evidence.
<- CLI dispatch
-> discovery, `EnterpriseClient`
! Upload retries must be idempotent; explicit relink is distinct from initial linkage.
! Content encoding, hashes, vendor identity, and linkage hints must survive round-trip unchanged.

### policies.register() / policies.handle()
File: enterprise/enterprise-cli/gator_enterprise_cli/commands/policies.py
Pulls active policy, writes machine and repo proof state, reports full-scope state, and renders drift.
Filesystem: machine policy cache and `.gator/policy-pin.json` (RW)
<- CLI dispatch
! Governed-repo detection walks to the repository root; invocation from a subdirectory must not drop the repo pin.
! A policy pin stores hashes and identity, never control-plane policy content.
! Full-scope reporting clears retired policies for named scopes; partial reports must not erase unrelated scope state.

### register(subparsers) / handle(args, client)
File: enterprise/enterprise-cli/gator_enterprise_cli/commands/*.py
Each command module owns parser registration and one dispatch handler; complex operations remain private helpers in that module.
<- `main()`
-> `EnterpriseClient`
! Parser registration and handler routing are a pair; a verb without both is an integration gap.

## Before Changing This Module

- Identify whether state is machine-scoped, repo-scoped, or server-scoped.
- Preserve idempotency for activation, hook installation, upload, and policy reporting.
- Check all vendor adapters when changing normalized transcript fields.
- Run `enterprise/tests` plus dispatcher and bundled-copy compatibility tests.

## Connections

-> [Enterprise Dispatcher](scripts-enterprise.md) - public base-wheel entry point
-> [Enterprise Server](scripts-enterprise-server.md) - HTTP and persistence contract
-> [Session Archaeology](scripts-session-archaeology.md) - shared evidence vocabulary
-> [Cross-Cutting](scripts-cross-cutting.md) - shipped-copy and product boundaries
-> [Contracts](contracts.md) - policy pins and marker schemas
