# Charter: Cross-Cutting Runtime Contracts

**Covers**: `src/gator_command/cli.py`, `src/gator_command/__init__.py`, `src/gator_command/scripts/gator_core.py`, `src/gator_command/scripts/gator_runtime.py`, `src/gator_command/scripts/gator_remote.py`, `pyproject.toml`, `src/gator_command/templates/gator-starter/scripts/enforcer-review.py`

Read this charter before the domain charter selected through [`INDEX.md`](INDEX.md). It contains only contracts that cross multiple domains.

## Owns

- Canonical charter-surface and repository-layout resolution.
- Shared script import and subprocess conventions.
- Runtime selection and managed Git-hook dispatch boundaries.
- Compatibility rules shared by CLI JSON, commit trailers, and shipped template mirrors.
- The boundary between the base Gator wheel and optional Enterprise code.

## Does Not Own

- Dashboard HTTP, content, or browser behavior; see [`scripts-dashboard.md`](scripts-dashboard.md), [`scripts-dashboard-shell.md`](scripts-dashboard-shell.md), [`scripts-dashboard-views.md`](scripts-dashboard-views.md) and [`scripts-dashboard-loop-ui.md`](scripts-dashboard-loop-ui.md).
- Session aggregation and provenance; see [`scripts-session-archaeology.md`](scripts-session-archaeology.md).
- Update planning, layout migration, or policy synchronization; see [`scripts-repo-lifecycle.md`](scripts-repo-lifecycle.md).
- Enterprise command or server behavior; see the Enterprise charters.
- Cumberland document styling; see [`contracts.md`](contracts.md).

## TRIPWIRE: Charter Surface Resolution

`gator_core.resolve_charter_surface(repo_root)` is the sole resolver for the governing charter directory, cross-cutting charter, and index. It must support both current `.gator/charters/` and legacy included layouts without requiring callers to reproduce layout tests.

! Pre-commit validation, charter tools, and session boot must consume this resolver. A local `Path.exists()` heuristic creates split governance.

## TRIPWIRE: Machine State Is Never a Repository

`~/.gator/` holds machine state (registry, machine id, adapters, hooks, Enterprise policy). It is never a project code repository, never a repository's Gator layer, and must never be made into a Git repository. Every `find_gator_root()` copy skips it (by location and by its `machine-id` / `dashboard-repos.json` files); a new repository resolver must apply the same rule. See `scripts-core-library.md` → `find_gator_root()`.

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

Loop watchers (CLI `start`/`extend` foreground hosts and Dashboard daemon threads) decide to stop from the **session**, not the event log: a terminal event ends a watch only while `session.json` is still terminal, because `max_rounds_exceeded` is resumable via `extend`. Any new watcher or poller that treats a terminal event as final must re-check the session. Every loop revival (start or extend) holds `start.lock` and refuses when another loop is active; see [`scripts-loop-host.md`](scripts-loop-host.md). The Dashboard serves requests concurrently (`DashboardHTTPServer`). Its own state locks (`_STATE_WRITE_LOCK`, `_STATE_LOCK`) are never held while a Loop OS lock (`start.lock`, `host.lock`, `session.lock`, the liveness lock) is acquired, and `_LOOP_HOSTS_LOCK` stays a leaf. The Loop locks remain the only authority for Loop transitions; see [`scripts-dashboard.md`](scripts-dashboard.md).

**`session.json` sharing violations:** on Windows, Loop saves and reads of `session.json` retry a transient sharing violation briefly, and never write the file in place. When retries run out, `loop/session.py` raises `SessionBusyError` (an `OSError` with errno `EBUSY`, not a `PermissionError`): nothing was written. Every consumer must treat it as "busy; retry". The Dashboard maps it to 503 "loop is busy; retry" (`_LOOP_LOCK_BUSY_ERRNOS`). The single-active guard `host.find_active_loop()` counts that loop as active (fail closed). Readers that catch `OSError` poll again. See [`scripts-loop-state.md`](scripts-loop-state.md).

## TRIPWIRE: Shipped-Copy Synchronization

Some runtime files intentionally exist in more than one delivery surface:

- package source under `src/gator_command/scripts/`;
- starter templates under `src/gator_command/templates/gator-starter/`;
- this repository's dogfood copy under `.gator/.includes/`;
- selected Enterprise bundled scripts under `enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/`.

When a file is governed by a byte-identity compatibility test, change all named copies in the same commit. Do not infer synchronization from similar filenames; consult the relevant contract test or domain charter. The pins:

- `TestWaitHandoffAlignment` (`tests/test_loop.py`): protocol-copy identity and content alignment across both protocol copies (the `/loop-join` template and live copy are retired, 2026-11-11; `test_slash_commands_are_retired` pins that neither exists), including the bounded `gator loop wait ... --max-seconds 360` command and the exit-3 reissue instruction; `test_protocol_documents_architect_extension` pins the Rule 10 text for the Architect-only max-rounds extension and participant re-engagement in both protocol copies; `test_protocol_state_table_matches_state_machine` pins the participant State Machine table and its Active/Paused/Terminal summary to `state_machine.ALL_STAGES` and the category sets (adding a stage without documenting it fails).
- `TestExecutiveSummaryProducerPaths`: the one-paragraph executive summary across all producer surfaces (protocol, artifact format reference), and that none still teaches "four bullets".
- `TestStructuredDecisionRequests`: the `decisions[]` session-schema contract and the escalate/unblock response lifecycle. `TestDurableArchitectResponses`: the `unblock --file` response-artifact contract and the pause-file rejection guard.
- `TestArtifactFormatAlignment`: artifact-format template headings, uncertainty classification language, and byte-identity between live and shipped copies.
- `TestEscalateVerdictWarning`: the soft ESCALATE-verdict guard warns only on actual `## Verdict` / `ESCALATE` patterns, not casual mentions; it is safe on non-UTF-8 input, while a planning review in a session with `contract.executive_summary` must be UTF-8 and is rejected cleanly otherwise.
- `TestByteIdentityAcrossThreeCopies` (`tests/test_multi_session.py`): the wheel-template and Enterprise bundled copies of `precommit_session.py`, `gator-session-start.py`, `precommit_override.py`, `gator-approve.py`, `precommit_lint.py`, `precommit_policy.py`, `precommit_charter.py` and `charter_significance.py`. `test_policy_module_matches_the_verifier_copy` also pins `charter_significance.py` to `src/gator_command/scripts/`, so the verifier and both hook runtimes run one significance policy (#105). `gator-pre-commit.py` is deliberately excluded (its copies differ); its override section is kept in step by hand plus `TestEnterpriseBundledRuntime`.
- `TestWindowsNativeProcessInfo` (same file): the start-time format shared by `gator-session-start.py` (recorder, PowerShell CIM `ToString('o')`) and `precommit_session.py` (Windows walker, native kernel32). The strings are compared exactly, so changing either side's format must change both.
- `TestEventArtifactPath`: the immutable `artifact_path` field on submission events (`draft_submitted`, `revision_requested`, `plan_approved`, `max_rounds_exceeded`), which the Dashboard timeline consumes. In sessions with `contract.executive_summary`, every participant submission event (those four plus `implementation_submitted`, `checkpoint_approved`, `implementation_approved`) also carries `executive_summary`, the author's normalized paragraph from the same captured text as its artifact; older events never have it and are never backfilled, so readers tolerate both (`tests/test_loop_executive_summary.py`).
- `TestParticipantDocs` (`tests/test_loop_attention.py`): byte-identity of the protocol and `loop-participant-watcher.md` pairs; protocol Rule 7 states there is no participant deadline, time words appear only in the legacy note, and the watcher note carries no time language.
- `tests/test_loop_codex_launcher.py`: byte-identity of the `codex-routine-participant-profile.md` template/dogfood pair, and `codex_launcher.RULE_TEXT` equals the rule documented in that note, so the launcher and the manual setup never grant different allow-lists.
- `TestGatorInitDocument` (`tests/test_init.py`): byte-identity of `templates/gator-starter/GATOR_INIT.md` and `.gator/.includes/GATOR_INIT.md`, and that the document points to the canonical sources without restating loop-protocol rules. `TestSessionOpeningHandoff` runs the same handoff assertions against both `gator-init.py` copies.
- `TestDriftGuards` (`tests/test_loop_context_evidence.py`): byte-identity of two live/shipped pairs (loop protocol and `loop-artifact-formats.md`); the shipped plan, findings, approval and implementation templates each pass `submit.executive_summary_problems()`; the shipped plan template has exactly one `## Context Checked` section that passes `submit.context_checked_problems()`, so the template never teaches a draft the CLI would reject; and the protocol names the Architect brief files and the Context Checked rules.

## TRIPWIRE: Machine-Local State Readers

Machine-local JSON readers return discriminated states such as `absent`, `malformed`, and `present`. Callers must not collapse malformed user configuration into absence: an invalid explicit preference fails closed, while an invalid runtime pin follows the hook fail-open contract above.

Paths persisted by Windows, MSYS, or POSIX callers are normalized through `normalize_path()` before filesystem checks. Registry writers must use the canonical helper rather than writing JSON directly.

Directory containment checks must test **both** `is_symlink()` and the reparse-point attribute (`_is_reparse_point`). On Windows a directory junction is a reparse point that `is_symlink()` does not report, so a symlink-only check lets a junction redirect reads outside a governed tree; per-file checks behind it cannot catch that. Domain instances: loop source directories (`scripts-loop-host.md`, TRIPWIRE "Source Loop Directories Are Contained"); Dashboard live discovery (`scripts-dashboard.md`, `_iter_live_candidates()`), where server-enumerated paths rely on the scanner's `DirEntry` reparse check plus resolve-equality, while direct-URL paths keep the full per-component walk in `_contained_repo_path()`.

## TRIPWIRE: CLI and Git Compatibility

**Python floor is 3.9** (`requires-python = ">=3.9"`; the `fast` CI matrix runs py3.9 on Ubuntu and Windows). Shipped code **and tests** must avoid 3.10+ APIs. Two have caught us: `Path.write_text(newline=...)` (use `write_bytes()`, or `open(..., newline=)`, as `tests/test_precommit_override.py` and `tests/test_vendor_cleanup.py` do) and runtime `X | Y` type unions. There is no local py3.9 on the main dev machine, so a grep for these before pushing is the check.

Machine-readable CLI output has a top-level `schema` identifier. Additive fields may remain within a version; removing, renaming, or changing meaning requires a schema bump and consumer migration. Readers tolerate the absence of every optional field below, because older output and older sessions never carry them and are never backfilled.

Loop turn windows (legacy loops) and Architect attention intervals (same stored field) have one validation authority: `loop/session.validate_turn_timeout()` (30..3600 s, integral). The loop CLI (`unblock --timeout`, legacy loops only; attention-mode loops refuse it) and the Dashboard HTTP endpoints (loop start `attention_interval` / alias `turn_timeout`, unblock `timeout` for legacy loops only, via `_validate_http_turn_timeout()`) both route through it; the browser mirrors the bounds only for early feedback. Do not re-implement the range at a call site. The per-extension round increment follows the same rule via `validate_round_count()` (1..20): CLI `extend --rounds` and Dashboard `/extend` (`_validate_http_round_count()`).

**Loop JSON and events (optional fields).**
- `gator-loop-status-v1`: `turn_timeout_seconds` / `turn_deadline` and the bounded-wait fields (status and wait); `checkpoint`, `checkpoints` and `generation` for declared checkpoint coding loops (`round` / `max_rounds` stay, informational there); `suspension`; `planning_source` (planning loops), `plan_source` (Architect-plan loops) and `revision`.
- `gator-loop-list-v1` items: `checkpoint_summary`, `planning_source`.
- `gator-loop-participant-v1` `still_waiting`: `suspended`, `stage`.
- Session: `status` keys `suspended_at`, `pause_reason`, `architect_message_for`, `architect_message_decision`; an optional `plan_source` block `{kind: "architect", artifact: "architect-plan.md", sha256, bytes}` (absent means an ordinary sketch loop) with turn type `initial_plan` (role architect); an optional `revision` block; `decisions[].response.kind` includes `cancelled_by_end`.
- Events: `checkpoint_approved` (non-terminal; `generation`, `checkpoint_id`, `accepted_tree`, `next_checkpoint_id`), `architect_plan_submitted` (non-terminal; `artifact_path`) and `loop_extended` (non-terminal; the audit record of an extension together with the Architect `extend` turn) are event types; other coding events carry `generation` and, for checkpoint loops, `checkpoint_*` / `findings_round`; `loop_started` carries `plan_source_kind`, `plan_sha256`, `plan_bytes` and, for revisions, `revision_source_loop_id`, `baseline_sha256`, `approval_sha256`, `approval_source_artifact`; `loop_ended_by_architect` carries `decision_id`. Timeline, tail and audit consumers tolerate all of them.
- `architect_message` / `architect_response_artifact` in participant status/wait JSON are populated only for their recipient role.
- **Participant exit contract:** exit `2` from model `status` / `wait` / `participant watch` means **terminal only**. A paused or blocked loop gives `status` `1` and `wait` `3` (bounded), and the watcher acknowledges `architect-block` and keeps watching. Participant prompts already wait on `1` and reissue on `3`. The protocol and watcher note pairs change together.
- CLI: `gator loop start` takes `--plan-file` and `--revise-from`. Dashboard: `POST /loops/start` accepts `plan_path` / `revise_from`; `/status` serves strict `planning_source` / `plan_source` / `revision` views; `/loops` items carry `planning_source`; the three fixed planning-source artifact names are served.
- Doc pairs (protocol, `loop-artifact-formats.md`) stay byte-identical under the drift guards above; `tests/test_loop_checkpoints.py` pins that the shipped plan template's `## Coding Checkpoints` parses valid.

**Approval resolution.** `approval_resolution` in `gator-loop-status-v1` and `gator-loop-coding-snapshot-v1`: `committed` comes from the first first-parent commit after the approved HEAD, and `commit` names that commit; `history_diverged` (stale) and `history_unavailable` (unknown) are reasons; `detached_mismatch` covers every moved detached HEAD; `identity: "governed" | "raw"` says which comparison was used (old sessions compare raw trees). `gator-loop-gitsnap-v1` carries the internal `approval_history` key (opt-in, never served), `governed_index_identity` and, in a `successor` `approval_history`, `governed_tree_identity` (`gov1:` digests that exclude `HOOK_MANAGED_PATHS`; null on failure), and the error code `git_permission_denied` (which `approval_resolution.reason` can carry as an unknown reason). The coding approval record carries `governed_identity` and the review `reviewed_governed_identity`. `gator-loop-coding-snapshot-v1` `live` may carry `guidance` on failure; the wording has one source, `gitsnap.error_guidance()` / `failure_text()`, and no surface parses Git text. The CLI and Dashboard reason texts change together. See `scripts-loop-state.md` → `resolve_approval()` and `scripts-loop-commands.md` TRIPWIRE "Raw Staged Tree Is Review Authority".

**Update output.** `gator-update-v1` carries `transient_untrack: {paths, count}`, `summary.transient_untrack` and `entry_point_actions` (always `[]`). `gator-update-result-v1` (`gator update --result-json`: `schema`, `version`, `exit_code`, `output`, `transient_untracked`) has one consumer, the Dashboard update relay, which tolerates its absence (raw-text fallback) and adds `transient_untracked` to its response. `gatorize.TRANSIENT_GATOR_FILES` must stay a superset of `precommit_override.HOOK_EPHEMERA_PATHS` (pinned in `tests/test_gatorize.py`). See `scripts-installer.md`, `scripts-repo-update.md`.

**State and init output.** `gator-state-v2` carries informational `native_files` and no entry points; Gator never writes `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` (see `scripts-installer.md`, `scripts-repo-update.md`, `scripts-managed-state.md`). `gator init --json` carries `session_opening`, whose `reads` may end with `gator-start-up.md` when a repo has no real charters; it carries no `charters` block. That output is unversioned and has no in-repo reader. Charter coverage for the Dashboard comes from `gator-repo-status.py` (`charter_coverage_pct`); see `scripts-repo-lifecycle.md`.

**Charter tool output.** `gator-charter-verify --json` carries top-level `charters: [{name, path, covers}]`; its only reader is the Dashboard charter sync check, which tolerates its absence, and the `/check` route and enforcer-review ignore it. It also carries additive `function_policy` (`default` | `strict`, #105), and `function-gap` findings carry an additive `reason`. `function-candidate` findings exist only under `--functions strict`, which no in-repo consumer requests. Coverage uses the shared `charter_covers` grammar, so glob-covered files are not `coverage-gap` and get the other checks. `gator charters report --json` (public subcommand `charters`, `gator-charters.py`) emits `gator-charters-report-v1`, read-only and additive within v1; its consumer, the Dashboard report relay, drops unknown keys rather than rejecting them. See `scripts-charter-tooling.md` → `build_report()`.

**Override CLI JSON.** `gator hook override status|approve|cancel|acknowledge --json` emits `gator-override-status-v1`, `gator-override-approve-v1`, `gator-override-cancel-v1` and `gator-override-acknowledge-v1` (closed refusal set); the status record's `pause_findings` / `draft_architect` are optional. The producers are both byte-identical `gator-approve.py` copies, and the consumer is the Dashboard override relay. The refusal codes and status `state` values are closed sets. The `revision` fingerprint is opaque, so consumers compare it for equality and never parse it. `gator-hook.py` routes its runtime advisory to stderr for these calls so stdout stays one JSON object. See `scripts-precommit.md`.

**Machine-local commit policy (`hook-mode-vocabulary-v2`).** The commit policy is per engineer and per clone. It lives in `$(git rev-parse --git-path gator-commit-policy.json)` (`precommit_local_policy.py`), is never tracked, and is `strict` when absent; the local levels are `strict | warn`. Neither hook copy reads the tracked `.gator/config.json` `enforcement_level`; a committed `warn`/`off` is ignored, with a warning. The Enterprise bundled hook falls back to `strict` when `GATOR_HOOK_MODE` is unset. The trailer `Gator-Commit-Policy: warn` marks a commit made under a relaxed policy; strict commits carry none. The Dashboard sets the policy through `POST /api/repo/<name>/commit-policy`. `precommit_local_policy.py` exists byte-identically in `templates/gator-starter/scripts/` and `scripts/` (as does `gator-enforce.py`), pinned by `tests/test_local_commit_policy.py`; `scripts/precommit_local_policy.py` is in `package-data`. See `scripts-precommit.md` (TRIPWIRE: The Commit Policy Is Machine-Local).

**Commit trailers.** Readers tolerate the presence or absence of every optional trailer on every historical commit.
- Commit readers accept both `Gator-Architect` and legacy `Gator-PI`; new commits emit `Gator-Architect`.
- Override trailers: `Gator-Override-Approved-By`, `Gator-Override-Block`, `Gator-Override-Reason` and `Gator-Override-Rules` (comma-separated rule names). All values are single-line and bounded by `precommit_override.sanitize_trailer_value()` so Architect input cannot inject trailers: `TRAILER_MAX` approver 80, reason 500 (older commits carry at most 200; readers must accept 500). `Gator-Charter-Changed: override-skip` appears only when an Architect approval overrode a charter rule, the charter escape hatch. `Gator-Override-*` is reserved for an actual external approval: a charter override, or a dangerous pattern in Enterprise `evidence_only`. Approvals carry a `resolution_policy` marker in `approval.json` (machine-local state, not a trailer).
- Acknowledgement trailers: `Gator-Dangerous-Patterns` (comma-separated `RULE@path:line` keys, never the matched source text; a key keeps its path's internal whitespace byte-for-byte, so readers split on `,` only) and `Gator-Dangerous-Pattern-Acknowledged-By` (the sanitized `architect` field). A recorded skip adds `Gator-Dangerous-Patterns-Unacknowledged` (comma-separated keys): the agent proceeded without an Architect decision. These are emitted only for evidence that validated against the commit's staged change and are not override evidence. `status.json` carries a `commit_checks` object (rule names and keys only).

The `change-type`, `significance`, vendor, and source-kind vocabularies are shared contracts. Update producers, schemas, compatibility tests, and consumers together.

**Commits view as a trailer and vocabulary consumer.** The Dashboard Commits view reads commit trailers through `dashboard/data.py` `get_repo_history()`, which projects every `Gator-*` trailer in order and folds legacy `Gator-PI` into `architect`. It renders them in `views/history.js`.
- **`change-type`:** `KINDS` labels every value in the producer's `VALID_CHANGE_TYPES`. An unknown value gets a neutral label. `tests/test_dashboard_ui/test_commits_view.py` fails if the producer adds a type the view does not label, so a vocabulary change must update the view too.
- **`significance`:** only `notable` gets a flag; any other value is shown as text.
- **Override trailers:** the view shows an override note only when one is present.
- **Acknowledgement trailers:** the view shows a separate "✓ Architect acknowledgement" note and "✓ Acknowledged" tag, never an override note, when `Gator-Dangerous-Patterns` is present.
- **`Gator-Machine-Id`:** shown only in the view's Raw trailers.

**Charter Sync as a trailer consumer.** `dashboard/charter_sync.py` `_commit_coverage()` reads `Gator-Charter-Changed` from its `git log`: `override-skip` (the Architect's charter approval) means a commit that skipped the charter is not flagged. Any other value, or no trailer (older commits), keeps the path-based rule. See `scripts-dashboard.md` → `run_sync()`.

See `scripts-dashboard.md` → `get_repo_history()` and `scripts-dashboard-views.md` → Commits view.

## TRIPWIRE: Product Boundary

The base `gator-command` wheel may expose the `gator enterprise` dispatcher but must not import Enterprise server dependencies or ship the Enterprise implementation package. Enterprise code stays under `enterprise/` and is installed separately.

Shared behavior needed by both products belongs behind an explicit library contract; do not copy Enterprise modules back into the base scripts tree.

## Package and License Surface

`src/gator_command/cli.py` is the installed command router. Adding or removing a public subcommand requires coordinated parser, packaging, help, and installed-wheel coverage. The top-level flags are `--version` and `--explain` (2.38.0), which dispatches to `scripts/gator-explain.py` (see `scripts-repo-lifecycle.md`). **Machine integration trigger:** `_ensure_machine_integration()` calls `machine_integration.ensure()` before dispatching every verb except `NO_ENSURE_VERBS` (`hook`, the hot path inside every vendor session; `integration`, so `remove` is not undone), and before `--explain`. Bare `gator`, `--help` and `--version` exit before it. Its lines go to stderr only (JSON stdout stays parseable); any exception becomes one stderr line and never changes the exit code; `GATOR_NO_VENDOR_INTEGRATION=1` skips it. `tests/conftest.py` sets that opt-out for the whole suite (subprocesses inherit it), so tests that run the real CLI never connect the test machine; only the trigger tests remove it. See `scripts-machine-integration.md`. `VERSION` and `pyproject.toml` version fields must agree; the release-candidate workflow validates this. `[tool.setuptools.package-data]` lists script files explicitly, so every new module under `scripts/` (for example `scripts/loop/liveness.py`, `scripts/loop/gitsnap.py`, `scripts/charter_covers.py`, `scripts/charter_significance.py`) must be added there; `tests/test_packaging.py` guards the gap. **Exception: Dashboard assets** ship through the `scripts/dashboard/**/*` glob (only `views/audit.js` is excluded), so a new `scripts/dashboard/views/*.js` or shell module such as `scripts/dashboard/workspace.js` needs no `package-data` entry. It must instead be added to both the script-tag regex and the inlined block in `dashboard/snapshot.py` `build_snapshot()`, or the offline snapshot keeps an external reference (`views/loop-markdown.js`, `workspace.js` and `views/charters.js` are examples, pinned by `tests/test_snapshot.py`). **Runtime read of starter templates (shipped HTML documents):** the Dashboard serves `templates/gator-starter/docs/{gator-overview,what-gator-can-do,gatorize-a-repo,start-a-session,gator-docs,gator-loop,gator-loop-extras,pre-commit-checks,charter-formation-process,charter-schema-v1,code-migrations}.html` at runtime for Welcome, the Docs view and the Loop Help and Extras tabs (`dashboard/helpers.WELCOME_DOCS_DIR` / `WELCOME_DOC_NAMES`, package-relative). It therefore depends on the `templates/**/*` package-data glob shipping them. Moving or renaming one breaks its topic: the route degrades to a plain-text 404, and the snapshot inlines `null`. The same files reach governed repositories through the generic `docs/` overlay in both `gatorize` (`action_install_gator()`) and `gator update` (`USER_TEMPLATE_DIRS["docs"]`); no installer code names them. Pinned by `tests/test_packaging.py::test_wheel_has_templates` and `tests/test_welcome_docs.py`.

Per-worktree Git-private state lives under `$(git rev-parse --git-path <name>)`: `gator-override/` (pre-commit override envelope), `gator-loop-liveness/` (loop participant liveness sidecar), `gator-charter-sync.json` (the Dashboard charter sync check's last summary, a display cache; see `scripts-dashboard.md` → `dashboard/charter_sync.py`) and `gator-charters-report.json` (the sanitized charter report, a display cache; see `scripts-dashboard.md` → `dashboard/charters_report.py`). None of them is ever staged, served by the Dashboard content APIs, or shared through the repository.

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
