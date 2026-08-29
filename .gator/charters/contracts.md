---
charter: contracts
scope: contracts/ — executable contract surface for the monorepo boundary
last-verified: 2026-08-02
---

# Charter: Contracts Layer

## Purpose

The `contracts/` directory is the **executable handshake** between the
base Gator install and the optional Enterprise capability, per Phase 2
of `.gator/artifacts/2026-07-21-monorepo-convergence-implementation-plan.md`.
Markdown-only contracts drift; every high-risk boundary here has a
companion pytest check that CI can enforce.

## Layout

```
contracts/
  README.md                            layer overview and running instructions
  schemas/
    gator-session-snippet-v2.json      JSON Schema — per-commit snippet
    gator-runtime-pin-v1.json          JSON Schema — .gator/runtime-pin.json (runtime-split Phase 1, 2026-08-18; emitted by gator_core.write_runtime_pin; resolver-read from Phase 2)
    gator-policy-pin-v1.json           JSON Schema — .gator/policy-pin.json (runtime-split Phase 5b, 2026-08-22; written by `gator-enterprise policies pull` in governed repos; hashes only, never content)
    gator-preferences-v1.json          JSON Schema — ~/.gator/preferences.json unified machine-local preferences file (machine-python-preference plan Phase 1, 2026-08-29; `python:` section populated in v2.10.0, `hooks:` section reserved for hook-mode follow-on plan)
    enterprise-config.json             JSON Schema — .gator/enterprise.json marker (consumed by gator_core.is_enterprise_active since 2026-08-01)
    gator-commit-summary-v1.md         Markdown spec — commit-summary frontmatter + sections
    gator-session-summary-v1.md        Markdown spec — vendor-session-summary frontmatter + sections
  reference/
    hook-mode-vocabulary.md            strict / warn / off enum
    machine-identity.md                ~/.gator/machine-id file format
    gator-directory-layout.md          Post-gatorize .gator/ tree
    presence-detection.md              How each half detects the other
  compatibility/
    __init__.py                        Package marker (scopes conftest.py)
    conftest.py                        Fixtures only (schemas_dir, fixtures_dir, reference_dir)
    _helpers.py                        parse_frontmatter helper (kept out of conftest.py)
    fixtures/                          Valid + invalid samples used by checks
    test_snippet_schema.py             33-schema pytest — validates fixtures + live snippets
    test_summary_schema.py             Commit + session summary pytest
    test_enterprise_marker.py          Schema + presence-detection reference impl (fail-closed)
    test_hook_modes.py                 Grep-verifies canonical enum in shipped code
    test_gator_layout.py               Runs gatorize into tmp dir, asserts layout
```

## Invariants (`!`)

- **! Executable contracts only.** Every schema or spec MUST have at
  least one companion pytest check. Markdown-only additions to
  `contracts/` are not a valid contract — they belong under
  `.gator/reference-notes/` or `procedures/`.

- **! Additive-friendly schemas.** JSON Schemas here MUST use
  `additionalProperties: true`. New fields are added freely without a
  version bump. Removing or renaming a required field IS a version
  bump — new schema filename, new `title`, old and new coexist for one
  release cycle.

- **! Filename-date grandfathering.** Live-check pytests that scan the
  repo for prior artifact instances MUST grandfather files whose
  filename-date prefix is before a documented lockdown date. Historical
  drift does not block the contract from tightening for new emissions.
  Current lockdown dates: `2026-07-01` for both snippets and commit
  summaries. Bump the constant in the test file when tightening.

- **! `contracts/compatibility/` is a package.** The `__init__.py`
  MUST stay in place — without it, the local `conftest.py` collides
  with `tests/conftest.py` under multi-dir pytest collection and every
  `tests/*` module that does `from conftest import load_script` breaks.

- **! CI MUST install `contracts/requirements.txt`.** The JSON-Schema
  tests use `pytest.importorskip("jsonschema")` for dev-local
  ergonomics; a CI runner without `jsonschema` would silently skip
  the load-bearing marker and snippet schema checks and report a false
  green. Any CI job that runs `pytest contracts/compatibility` MUST
  install this file first.

- **! Fail-closed presence detection.** The reference implementation
  in `test_enterprise_marker.py::_is_enterprise_active` MUST return
  False on any of: missing marker, unreadable marker, malformed JSON,
  non-object JSON root, `enabled != true`. **Production impl landed
  2026-08-01** as `gator_core.is_enterprise_active` (see
  `scripts-core-library.md`); `tests/test_gator_core.py::TestIsEnterpriseActive`
  pins its semantics against this contract (12 cases including 6-way
  non-object-root sweep — Codex Phase 4b flagged that both impls
  crashed on `[]`/`42`/`"foo"` instead of returning False; both were
  patched in the same commit that added the parametrized coverage).
  Any Phase 4 Enterprise gating code MUST call
  `gator_core.is_enterprise_active` rather than re-implementing the
  check — divergence between call sites is the exact regression this
  invariant defends against. **Phase 4e restructure (2026-08-02)**:
  command bodies (including `status`, the original Phase 4c-A adopter
  at `gator-enterprise.py::cmd_status`) moved into
  `enterprise/enterprise-cli/gator_enterprise_cli/`; the base-wheel
  `gator-enterprise.py` is now a thin dispatcher with no command bodies
  and no direct `is_enterprise_active` call. The dispatcher's post-4e
  responsibility is degraded-mode routing (three ordered checks:
  package importable, `.main` importable, verb in `ENTERPRISE_CLI_VERBS`;
  hardened by whiteboard Finding 1 fix, see `scripts-enterprise.md`).
  **2026-08-09 (Phase 4 — 3.0 stabilization P1.1 + P2.1)**: dispatcher
  verb tables reconciled with reality — `CLIENT_SUBCOMMANDS` now names
  the real developer verbs (`activate/sync/repo/transcripts/commits`);
  `SERVER_SUBCOMMANDS` names the real operator/admin verbs (`auth/
  repos/providers/policies/reports/machines/blocks`); `ENTERPRISE_CLI_VERBS`
  extended with `transcripts` + `commits` (the two MVP verbs that had
  been advertised nowhere and rejected everywhere). Regression pin:
  `tests/test_gator_enterprise.py::TestConstants::test_every_advertised_verb_is_mapped`.
  **Integration gap (post-cutover polish)**: the ported enterprise-cli
  command modules do NOT currently call `is_enterprise_active` — they
  were ported from enterprise-mvp which was designed as a standalone
  server operator CLI, not a per-repo gated flow. The gating contract
  still applies to any NEW per-repo gating code added to enterprise-cli
  post-cutover; that reconciliation is tracked as post-cutover
  integration work per Architect direction.
  **Phase 4c-B** added `enterprise_vendor_hooks.install_enterprise_vendor_hooks`
  as a MACHINE-scoped concern that does NOT read the marker itself —
  it is gated at the CLI layer by the operator's explicit `--install-hooks`
  opt-in on `gator enterprise activate` (renamed from the earlier docstring's
  `setup` per the 2026-08-09 P2.1 verb reconciliation), not by an
  `is_enterprise_active` check. Distinct decision surface: the marker gates Enterprise-side
  behavior on a repo; the --install-hooks flag gates machine-level
  side effects on other tools' settings. The vendor-hooks module also
  fail-closes on wrong-shape settings files (malformed JSON,
  non-object root, or non-dict `hooks` key) — Codex Phase 4c-B review
  caught a real clobber bug where wrong-shape `hooks` values were
  silently replaced; fixed to match base Gator's `gator-update.py`
  correct semantics + covered by parametrized regression tests.
  **Phase 4c-C-2** added an optional `repo_id` field to
  `enterprise-config.json` — server-assigned repository identifier
  used by `enterprise_client.pull_policies(repo_id)`. Optional by
  design: pre-4c-C-2 markers lack the field and stay valid; `sync`
  gracefully skips the pull when it's absent (auth-only report) while
  `audit` (fleet-scoped) works without it. The field is documented in
  the schema description with a link to the endpoint that uses it.
  Post-shipment Codex review caught that the schema's `allOf/if` rule
  requiring `api_url` when `enabled=true` was NOT mirrored in the
  production `_load_marker_and_credentials()` runtime check — a marker
  with `enabled` but no `api_url` crashed the client with KeyError.
  Fixed to validate `api_url` presence + string type before construction;
  the schema-side invariant and the runtime check now match.
  **Phase 4d-substrate** (2026-08-02) tracks server-side Migration 008
  (`enterprise/migrations/versions/008_transcript_session_id.py`) —
  adds `transcript_session_id VARCHAR(255) NULL` to the `commits` table.
  This completes the client → server pipe for the `transcript_session_id`
  field that `gator-session-snippet-v2` (contracts/schemas) has emitted
  since Phase 4a: the client-side snippet writes the vendor session ID
  from `.gator/active-vendor-session.json` into every committed snippet;
  Migration 008 gives the server the column to store it on ingest. The
  snippet field is required on the client side; the server-side column
  is nullable (server may receive snippets from clients pre-4a that
  don't populate the field). No new schema version bump on the snippet
  side — 4a's addition was already compatible.
  **Phase 4c-C-1** added `enterprise_credentials` as a second
  MACHINE-scoped module (`~/.gator/enterprise/credentials.json`).
  `setup` persists the api-key there (marker itself stays credential-free
  by design — scope separation invariant in `scripts-enterprise.md`),
  and `read_credentials` fail-closes on the same shape classes as
  `is_enterprise_active`: missing file, malformed JSON, non-object
  root all return `None`. The fail-closed posture propagates through
  both files' checks — future sync/audit code (4c-C-2) must handle
  `read_credentials() is None` as "not configured" and never assume
  a returned dict has any specific shape beyond `{"api_key": str}`.
  Post-shipment Codex Phase 4c-C-1 review caught a write-ordering
  bug: earlier `cmd_setup` wrote the marker first and crashed
  uncaught on credential-write failures, leaving repos
  Enterprise-marked but unauthenticated. Fixed by reversing the order
  (credentials first, marker second) with explicit try/except on both
  writes — see `scripts-enterprise.md` invariant "cmd_setup writes
  credentials BEFORE marker; both writes are guarded".

- **! Never convert contract failures to skips.** Contract tests that
  invoke real product code (`test_gator_layout.py` runs `git init` +
  `action_install_gator`) MUST let exceptions propagate as test
  failures. `pytest.skip` is only appropriate when the environment
  genuinely cannot host the check (no `git` binary, no
  `.gator/session-snippets/` directory, no post-lockdown files to
  scan) — never as a swallow for an installer regression.

## Files → functions

| File | Key symbols | Reads | Writes |
|---|---|---|---|
| `contracts/compatibility/conftest.py` | `schemas_dir`, `fixtures_dir`, `reference_dir` fixtures | filesystem paths | nothing |
| `contracts/compatibility/_helpers.py` | `parse_frontmatter(md_text) → (dict, str)` | nothing | nothing |
| `contracts/compatibility/test_snippet_schema.py` | `test_schema_is_itself_valid`, `test_valid_snippet_passes`, `test_missing_required_fails`, `test_wrong_schema_tag_fails`, `test_live_repo_snippets_conform` | schema JSON, fixtures, live `.gator/session-snippets/*.json` | nothing |
| `contracts/compatibility/test_policy_pin.py` | `test_schema_is_itself_valid`, `test_schema_identifies_itself_as_v1`, `test_schema_is_additive_friendly`, `test_valid_pin_passes`, `test_empty_policies_array_is_legal`, `test_bad_hash_format_fails`, `test_missing_policies_fails`, `test_live_repo_pin_conforms` (skips pre-first-pull) | schema JSON, fixtures, live `.gator/policy-pin.json` | nothing |
| `contracts/compatibility/test_runtime_pin.py` | `test_schema_is_itself_valid`, `test_schema_identifies_itself_as_v1`, `test_schema_is_additive_friendly`, `test_valid_pin_passes`, `test_missing_manifest_fails`, `test_wrong_schema_tag_fails`, `test_malformed_manifest_digest_fails`, `test_live_repo_pin_conforms` (skips pre-Phase-1; no date-grandfathering — new artifact class, every instance postdates the contract) | schema JSON, fixtures, live `.gator/runtime-pin.json` | nothing |
| `contracts/compatibility/test_preferences_schema.py` | `test_schema_is_itself_valid`, `test_schema_identifies_itself_as_v1`, `test_schema_is_additive_friendly`, `test_hooks_section_is_reserved_stub` (forward-compat pin for the hook-mode follow-on plan), `test_valid_preferences_pass`, `test_wrong_schema_tag_fails`, `test_missing_schema_fails`, `test_python_section_optional`, `test_hooks_section_only_is_legal` (forward-compat), `test_unknown_top_level_section_tolerated`, `test_python_source_enum_enforced`, `test_updated_at_pattern_enforced`, `test_live_machine_preferences_conforms` (skips when `~/.gator/preferences.json` absent — the default state) | schema JSON, fixtures, live `~/.gator/preferences.json` | nothing |
| `contracts/compatibility/test_summary_schema.py` | parametrized `test_commit_summary_frontmatter`, `test_commit_summary_body_sections`, `test_live_commit_summaries_conform`, `test_session_summary_frontmatter`, `test_session_summary_body_sections`, `test_live_session_summaries_conform`, spec-present checks | spec + fixture files, live `.gator/sessions/*commit*.md` and `.gator/sessions/*.md` with `schema: gator-session-summary-v1` | nothing |
| `contracts/compatibility/test_enterprise_marker.py` | marker validity + `_is_enterprise_active` reference impl + fail-closed tests | schema JSON, fixtures, `tmp_path` | temp `.gator/enterprise.json` |
| `contracts/compatibility/test_hook_modes.py` | `test_gator_enforce_uses_canonical_enum`, `test_pre_commit_hook_validates_against_canonical_enum`, `test_default_config_stub_uses_strict` | shipped script sources | nothing |
| `contracts/compatibility/test_gator_layout.py` | imports `gatorize.action_install_gator` via `importlib` and runs into `tmp_path`; asserts layout marker, stubs, `.includes/`, machine-id KV format. **Runtime-split Phase 4 (2026-08-19)**: `scripts` removed from `REQUIRED_DIRS_INCLUDES`; now asserts the Phase-4 shape — `.includes/scripts/` ABSENT on fresh installs + `.gator/runtime-pin.json` present, schema-tagged `gator-runtime-pin-v1`, with a non-empty wheel-sourced manifest | `src/gator_command/scripts/gatorize.py`, `tmp_path` | tmp `.gator/` tree |

## Called by (`←`)

- `pytest.ini` — `testpaths = tests contracts/compatibility`.
- Nothing in shipped runtime code depends on `contracts/`. It is
  compile-time-and-CI-only.

## Calls out (`→`)

- `jsonschema.Draft202012Validator` (optional dependency) — required
  only for `test_snippet_schema.py` and `test_enterprise_marker.py`.
  Both use `pytest.importorskip("jsonschema")` so the rest of the
  suite runs on a bare interpreter.
- `src/gator_command/scripts/gatorize.py::action_install_gator` — via
  `importlib` in `test_gator_layout.py`. Grep-anchored.
- Shipped script source at
  `src/gator_command/templates/gator-starter/scripts/{gator-enforce,gator-pre-commit}.py`
  and `src/gator_command/scripts/gatorize.py` — read as text via
  `Path.read_text()` in `test_hook_modes.py`. Grep-anchored substring
  matches. If the source path structure changes, `test_hook_modes.py`
  falls back to `.gator/.includes/scripts/` as a secondary search.

## Adding a contract

1. Write the schema or spec under `schemas/` (JSON Schema for
   structured data, markdown-with-frontmatter for humans+machines).
2. Add fixtures under `compatibility/fixtures/` — one valid, one
   invalid minimum.
3. Add a pytest file (or extend an existing one) under
   `compatibility/`.
4. Update this charter's "Files → functions" table with the new
   symbols.
5. If the contract is greenfield (no code yet emits or reads it),
   mark it as such in the spec header.

## Connections

→ [Cross-Cutting](scripts-cross-cutting.md) — governance obligations
  the contracts layer participates in.
→ Plan artifact: `../../artifacts/2026-07-21-monorepo-convergence-implementation-plan.md`
  Phase 2 exit criteria.
→ Decision record: `../../artifacts/2026-07-31-monorepo-product-contract-decisions.md`
  Naming, evidence default, packaging boundary.
