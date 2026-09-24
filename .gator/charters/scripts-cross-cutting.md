# Charter: Cross-Cutting Runtime Contracts

**Covers**: `src/gator_command/cli.py`, `src/gator_command/__init__.py`, `src/gator_command/scripts/gator_core.py`, `src/gator_command/scripts/gator_runtime.py`, `src/gator_command/scripts/gator_remote.py`, `pyproject.toml`

Read this charter before the domain charter selected through [`INDEX.md`](INDEX.md). It contains only contracts that cross multiple domains.

## Owns

- Canonical charter-surface and repository-layout resolution.
- Shared script import and subprocess conventions.
- Runtime selection and managed Git-hook dispatch boundaries.
- Compatibility rules shared by CLI JSON, commit trailers, and shipped template mirrors.
- The boundary between the base Gator wheel and optional Enterprise code.

## Does Not Own

- Dashboard HTTP, content, or browser behavior; see [`scripts-dashboard.md`](scripts-dashboard.md) and [`scripts-dashboard-ui.md`](scripts-dashboard-ui.md).
- Session aggregation and provenance; see [`scripts-session-archaeology.md`](scripts-session-archaeology.md).
- Update planning, layout migration, or policy synchronization; see [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md).
- Enterprise command or server behavior; see the Enterprise charters.
- Cumberland document styling; see [`contracts.md`](contracts.md).

## TRIPWIRE: Charter Surface Resolution

`gator_core.resolve_charter_surface(repo_root)` is the sole resolver for the governing charter directory, cross-cutting charter, and index. It must support both current `.gator/charters/` and legacy included layouts without requiring callers to reproduce layout tests.

! Pre-commit validation, charter tools, and session boot must consume this resolver. A local `Path.exists()` heuristic creates split governance.

## TRIPWIRE: Import Boundaries

Scripts loaded by filename use `gator_core.import_sibling(name)` rather than package-relative imports because fleet copies may execute outside an installed package. Callers must handle both exceptions and a `None` result for a missing sibling.

Optional enrichment imports degrade only the affected section. Keep independent imports in independent guards so one absent feature does not disable unrelated output.

`ensure_utf8_stdout()` is called from executable entry points before Unicode output. Do not scatter platform-specific encoding mutations through domain code.

## TRIPWIRE: Git Wrapper Contract

Shared `git(*args, cwd=None)` helpers return stripped stdout on success and a falsey result on expected Git failure. Callers that require error classification must use a dedicated subprocess seam and inspect the return code; do not silently change the shared return type.

Local and remote readers that feed the same consumer must return the same schema. Remote absence may produce a structured unavailable state, never a locally shaped payload containing another repository's data.

## TRIPWIRE: Runtime and Hook Dispatch

`resolve_governed_runtime(repo_root, cli_version=None)` selects the runtime for repo hooks. A corrupt or missing runtime pin fails open to the repo-shipped scripts so governance damage does not brick Git operations.

Managed Git hooks live under the configured `core.hooksPath`; legacy `.git/hooks` is a compatibility probe, not a second authority. Hook installers and health checks must agree on the canonical directory.

`gator hook session-open` and `session-start` resolve the Git top level before governance lookup. Commit hooks retain their existing working-directory contract. See [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md).

## TRIPWIRE: Shipped-Copy Synchronization

Some runtime files intentionally exist in more than one delivery surface:

- package source under `src/gator_command/scripts/`;
- starter templates under `src/gator_command/templates/gator-starter/`;
- this repository's dogfood copy under `.gator/.includes/`;
- selected Enterprise bundled scripts under `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/`.

When a file is governed by a byte-identity compatibility test, change all named copies in the same commit. Do not infer synchronization from similar filenames; consult the relevant contract test or domain charter. `TestWaitHandoffAlignment` in `tests/test_loop.py` pins protocol-copy identity and content alignment across the loop-join template, entry-point renderer, and live entry-point files. `TestExecutiveSummaryProducerPaths` pins the executive summary requirement across all producer surfaces (entry-point renderer, loop-join command template, protocol, and artifact format reference). `TestStructuredDecisionRequests` in the same file pins the `decisions[]` session-schema contract and the escalate/unblock response lifecycle. `TestDurableArchitectResponses` pins the `unblock --file` response-artifact contract and the pause-file rejection guard. `TestArtifactFormatAlignment` pins artifact-format template headings, uncertainty classification language, and byte-identity between live and shipped copies. `TestEscalateVerdictWarning` pins the soft ESCALATE-verdict detection guard: warns only on actual `## Verdict` / `ESCALATE` patterns, not casual mentions; safe on non-UTF-8 input. `TestEventArtifactPath` pins the immutable `artifact_path` field on submission events (`draft_submitted`, `revision_requested`, `plan_approved`, `max_rounds_exceeded`) — the contract the Dashboard timeline consumes.

## TRIPWIRE: Machine-Local State Readers

Machine-local JSON readers return discriminated states such as `absent`, `malformed`, and `present`. Callers must not collapse malformed user configuration into absence: an invalid explicit preference fails closed, while an invalid runtime pin follows the hook fail-open contract above.

Paths persisted by Windows, MSYS, or POSIX callers are normalized through `normalize_path()` before filesystem checks. Registry writers must use the canonical helper rather than writing JSON directly.

## TRIPWIRE: CLI and Git Compatibility

Machine-readable CLI output has a top-level `schema` identifier. Additive fields may remain within a version; removing, renaming, or changing meaning requires a schema bump and consumer migration.

Commit readers accept both `Gator-Architect` and legacy `Gator-PI`. New commits emit `Gator-Architect`; historical trailers remain valid input.

The `change-type`, `significance`, vendor, and source-kind vocabularies are shared contracts. Update producers, schemas, compatibility tests, and consumers together.

## TRIPWIRE: Product Boundary

The base `gator-command` wheel may expose the `gator enterprise` dispatcher but must not import Enterprise server dependencies or ship the Enterprise implementation package. Enterprise code stays under `enterprise/` and is installed separately.

Shared behavior needed by both products belongs behind an explicit library contract; do not copy Enterprise modules back into the base scripts tree.

## Package and License Surface

`src/gator_command/cli.py` is the installed command router. Adding or removing a public subcommand requires coordinated parser, packaging, help, and installed-wheel coverage.

The repository is Apache-2.0. Preserve `LICENSE`, `NOTICE`, and contributor provenance requirements when adding third-party assets or code.

## Before Changing Cross-Cutting Seams

- Identify every producer and consumer of the contract.
- Check for package, template, dogfood, and Enterprise bundled copies.
- Preserve fail-open versus fail-closed behavior deliberately.
- Run the relevant compatibility tests plus the affected domain suite.
- Keep implementation history in Git or an artifact, not in this always-read charter.

## Connections

-> [Core Library](scripts-core-library.md) - shared helpers and runtime APIs
-> [Repo Lifecycle](scripts-repo-lifecycle.md) - hook installation and dispatch
-> [Session Archaeology](scripts-session-archaeology.md) - snippets, summaries, and provenance
-> [Dashboard Server](scripts-dashboard.md) - registry, HTTP trust boundaries, and removal endpoint
-> [Enterprise Dispatcher](scripts-enterprise.md) - base-wheel separation
-> [Contracts](contracts.md) - schemas and byte-identity checks
-> [Release Pipeline](release-pipeline.md) - installed-wheel and workflow validation
