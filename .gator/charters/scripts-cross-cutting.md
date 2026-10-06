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

Loop watchers (CLI `start`/`extend` foreground hosts and Dashboard daemon threads) decide to stop from the **session**, not the event log: a terminal event ends a watch only while `session.json` is still terminal, because `max_rounds_exceeded` is resumable via `extend` (#39). Any new watcher or poller that treats a terminal event as final must re-check the session. Every loop revival (start or extend) holds `start.lock` and refuses when another loop is active; see [`scripts-loop.md`](scripts-loop.md).

## TRIPWIRE: Shipped-Copy Synchronization

Some runtime files intentionally exist in more than one delivery surface:

- package source under `src/gator_command/scripts/`;
- starter templates under `src/gator_command/templates/gator-starter/`;
- this repository's dogfood copy under `.gator/.includes/`;
- selected Enterprise bundled scripts under `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/`.

When a file is governed by a byte-identity compatibility test, change all named copies in the same commit. Do not infer synchronization from similar filenames; consult the relevant contract test or domain charter. `TestWaitHandoffAlignment` in `tests/test_loop.py` pins protocol-copy identity and content alignment across the loop-join template (and its live `.claude/commands/` copy), entry-point renderer, and live entry-point files — including the bounded `gator loop wait ... --max-seconds 45` command and the exit-3 reissue instruction — and (`test_protocol_documents_architect_extension`) the Rule 10 text for the Architect-only max-rounds extension and participant re-engagement in both protocol copies; `test_protocol_state_table_matches_state_machine` pins the participant State Machine table and its Active/Paused/Terminal summary to `state_machine.ALL_STAGES` / category sets (adding a stage without documenting it fails). `TestExecutiveSummaryProducerPaths` pins the executive summary requirement across all producer surfaces (entry-point renderer, loop-join command template, protocol, and artifact format reference). `TestStructuredDecisionRequests` in the same file pins the `decisions[]` session-schema contract and the escalate/unblock response lifecycle. `TestDurableArchitectResponses` pins the `unblock --file` response-artifact contract and the pause-file rejection guard. `TestArtifactFormatAlignment` pins artifact-format template headings, uncertainty classification language, and byte-identity between live and shipped copies. `TestEscalateVerdictWarning` pins the soft ESCALATE-verdict detection guard: warns only on actual `## Verdict` / `ESCALATE` patterns, not casual mentions; safe on non-UTF-8 input. `TestByteIdentityAcrossThreeCopies` (tests/test_multi_session.py) pins the wheel-template vs Enterprise bundled copies of `precommit_session.py`, `gator-session-start.py`, `precommit_override.py`, `gator-approve.py`, and `precommit_lint.py`; `gator-pre-commit.py` is deliberately excluded (pre-existing drift) and its override section is kept in step by hand plus `TestEnterpriseBundledRuntime`. `TestEventArtifactPath` pins the immutable `artifact_path` field on submission events (`draft_submitted`, `revision_requested`, `plan_approved`, `max_rounds_exceeded`) — the contract the Dashboard timeline consumes. `TestParticipantDocs` in `tests/test_loop_attention.py` (#47) pins byte-identity of the protocol, `loop-participant-watcher.md` and `/loop-join` pairs. It also pins that protocol Rule 7 states there is no participant deadline, that time words appear only in the legacy note, and that `/loop-join` and the watcher note carry no time language. `TestDriftGuards` in `tests/test_loop_context_evidence.py` (#43/#46) pins byte-identity of three live/shipped pairs (loop protocol, `loop-artifact-formats.md`, and `/loop-join` in `.claude/commands/` vs the starter template). It also pins that the shipped plan template contains exactly one `## Context Checked` section that passes `submit.context_checked_problems()`, so the template can never teach a draft the CLI would reject, and that the protocol and `/loop-join` name the Architect brief files and the Context Checked rules.

## TRIPWIRE: Machine-Local State Readers

Machine-local JSON readers return discriminated states such as `absent`, `malformed`, and `present`. Callers must not collapse malformed user configuration into absence: an invalid explicit preference fails closed, while an invalid runtime pin follows the hook fail-open contract above.

Paths persisted by Windows, MSYS, or POSIX callers are normalized through `normalize_path()` before filesystem checks. Registry writers must use the canonical helper rather than writing JSON directly.

## TRIPWIRE: CLI and Git Compatibility

Machine-readable CLI output has a top-level `schema` identifier. Additive fields may remain within a version; removing, renaming, or changing meaning requires a schema bump and consumer migration. Example: `gator-loop-status-v1` gained `turn_timeout_seconds` / `turn_deadline` (status and wait) and bounded-wait fields additively; the Dashboard and agents must tolerate their absence in older output.

Loop turn windows (legacy) and Architect attention intervals (#47; same stored field) have one validation authority: `loop/session.validate_turn_timeout()` (30..3600 s, integral). The loop CLI (`unblock --timeout`, legacy loops only; attention-mode loops refuse it) and the Dashboard HTTP endpoints (loop start `attention_interval` / alias `turn_timeout`, unblock `timeout` for legacy loops only, via `_validate_http_turn_timeout()`) must both route through it; the browser mirrors the bounds only for early feedback. Do not re-implement the range at a call site. The per-extension round increment follows the same rule via `validate_round_count()` (1..20) — CLI `extend --rounds` and Dashboard `/extend` (`_validate_http_round_count()`).

**#55 checkpoints.**
- `gator-loop-status-v1` gains additive `checkpoint`, `checkpoints` and `generation` for declared checkpoint coding loops. `round` and `max_rounds` remain, and are informational for those loops.
- `gator-loop-list-v1` items gain additive `checkpoint_summary`.
- `checkpoint_approved` is an additive, **non-terminal** `events.jsonl` event type, emitted on a non-final checkpoint approval with `generation`, `checkpoint_id`, `accepted_tree` and `next_checkpoint_id`. Other coding events gain additive `generation` and, for checkpoint loops, `checkpoint_*` / `findings_round` fields.
- Doc pairs touched (protocol, `loop-artifact-formats.md`, `/loop-join`) stay byte-identical under the existing drift guards. `tests/test_loop_checkpoints.py` also pins that the shipped plan template's `## Coding Checkpoints` parses valid.

**#53 suspension state (additive).**
- **Session `status`** gains `suspended_at`, `pause_reason`, `architect_message_for` and `architect_message_decision`. An absent key keeps legacy behaviour.
- **Decision responses:** `decisions[].response.kind` gains `cancelled_by_end`, and the `loop_ended_by_architect` event gains `decision_id`.
- **Participant status/wait JSON:** `architect_message` / `architect_response_artifact` keep their keys but are populated only for their recipient role. Readers must tolerate all of these.
- **Participant exit contract (meaning change, deliberate):** exit `2` from model `status` / `wait` / `participant watch` means **terminal only**. A paused or blocked loop gives `status` `1` and `wait` `3` (bounded), and the watcher acks `architect-block` and keeps watching.
  - `gator-loop-status-v1` gains additive `suspension` (model, Architect and wait JSON).
  - `gator-loop-participant-v1` `still_waiting` gains additive `suspended` / `stage`.
  - Old participant prompts stay safe because they already wait on `1` and reissue on `3`. The protocol, watcher note, `/loop-join` pairs, `render_entry_content` and the live CLAUDE.md / AGENTS.md / GEMINI.md managed regions change together.

`loop_extended` (#39) is an additive `events.jsonl` event type and is NOT terminal; timeline, tail, and audit consumers must tolerate it. The loop session schema is unchanged by extension — the audit record is the `loop_extended` event plus the Architect `extend` turn.

Commit readers accept both `Gator-Architect` and legacy `Gator-PI`. New commits emit `Gator-Architect`; historical trailers remain valid input.

Override audit trailers (#34, #35) are additive: `Gator-Override-Approved-By` and `Gator-Override-Block` (pre-existing), plus `Gator-Override-Reason` and `Gator-Override-Rules` (comma-separated rule names). All values are single-line and bounded by `precommit_override.sanitize_trailer_value()` so Architect input cannot inject trailers. Readers must tolerate their presence or absence. `Gator-Charter-Changed: override-skip` now appears only when a charter rule was overridden (a lint-only override keeps `yes`/`no`).

The `change-type`, `significance`, vendor, and source-kind vocabularies are shared contracts. Update producers, schemas, compatibility tests, and consumers together.

## TRIPWIRE: Product Boundary

The base `gator-command` wheel may expose the `gator enterprise` dispatcher but must not import Enterprise server dependencies or ship the Enterprise implementation package. Enterprise code stays under `enterprise/` and is installed separately.

Shared behavior needed by both products belongs behind an explicit library contract; do not copy Enterprise modules back into the base scripts tree.

## Package and License Surface

`src/gator_command/cli.py` is the installed command router. Adding or removing a public subcommand requires coordinated parser, packaging, help, and installed-wheel coverage. `VERSION` and `pyproject.toml` version fields must agree; the release-candidate workflow validates this. `[tool.setuptools.package-data]` lists script files explicitly, so every new module under `scripts/` (for example `scripts/loop/liveness.py`) must be added there, as with `scripts/loop/gitsnap.py` (#41); `tests/test_packaging.py` guards the gap. **Exception: Dashboard assets** ship through the `scripts/dashboard/**/*` glob (only `views/audit.js` is excluded), so a new `scripts/dashboard/views/*.js` needs no `package-data` entry. It must instead be added to both the script-tag regex and the inlined block in `dashboard/snapshot.py` `build_snapshot()`, or the offline snapshot keeps an external reference. `views/loop-markdown.js` (#45) is the example, pinned by `tests/test_snapshot.py`.

Per-worktree Git-private state lives under `$(git rev-parse --git-path <name>)`: `gator-override/` (pre-commit override envelope) and `gator-loop-liveness/` (loop participant liveness sidecar, #36). Both are never staged, never served by the Dashboard content APIs, and never shared through the repository.

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
