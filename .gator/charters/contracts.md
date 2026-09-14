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
    gator-blueprint-html-v1.md         Markdown spec — HTML artifact protocol for `.gator/blueprints/*.html` files (HTML-artifact-protocol plan Release A, v2.12.0; four doc classes charter-map / feature-blueprint / procedure-visual / reference-explainer; two shipped templates `_template.html` + `_template-narrative.html`)
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

- **! B1 Dashboard content-transport response contract (v2.13.0).**
  Every response from a B1-owned endpoint (`/files`, `/file`,
  `/raw`, `/history/<file>`) MUST satisfy the following invariants,
  enforced by Slice 1 helpers in `gator-dashboard.py` and Slice 2's
  in-place `do_GET` migration:
  - **Parse-once invariant.** `_parse_request(handler)` runs
    EXACTLY ONCE per request from `do_GET` before any handler
    dispatch. B1-owned handlers (`_handle_files`, `_handle_file`,
    `_handle_raw`, `_handle_history`) accept `req` as an argument
    and MUST NOT read `handler.path` or invoke `_parse_request`
    again. Legacy pass-through branches (existing shipped
    `if path.startswith(...)` chain) are exempt only because they
    predate B1.
  - **Wire-schema invariant.** Every `/files` response entry —
    live OR historical — is minted by
    `_serialize_listing_entry(namespace_root, disk_rel, name,
    size, mtime=None)` in `dashboard/content_policy.py`. Three
    namespace shapes exist; an unknown value raises `ValueError`
    (no silent mislabel at the security boundary):
    - source (`""`) → `path="source/<disk_rel>"`, `source="repo"`
    - `.gator` → `path="<disk_rel>"`, `source=".gator"`
    - `gator-command` → `path="gator-command/<disk_rel>"`,
      `source="gator-command"`
  - **One-canonical-path invariant.** Every governance document
    has EXACTLY ONE canonical URL under `/file`, `/raw`,
    `/history`, and `/files`. `parse_logical_path` rejects explicit
    `.gator/` prefixes (namespace is implicit); `is_browsable`
    rejects `source/.gator/…` and `source/gator-command/…`
    aliases. A `source/` URL MUST NOT resolve to a governance
    document even if the underlying file exists.
  - **Discovery-serving visibility invariant.** For every
    `(endpoint, path, ?version=)` tuple, the answer returned by
    discovery (`/files`, `/files?version=`) MUST agree with the
    answer returned by serving (`/file`, `/raw`, `/file?version=`,
    `/raw?version=`). Live-scanner entries pass through
    `parse_logical_path` + `is_browsable` before emit; the
    historical `git ls-tree` re-parse uses the same predicate.
  - **Transport-headers invariant.** Every B1-owned response
    (raw or JSON, success or error) carries
    `X-Content-Type-Options: nosniff` unconditionally. JSON
    responses use exact Content-Type
    `application/json; charset=utf-8` via the extended
    `_send_json`. Any response that consumed a `?version=` key
    carries `Cache-Control: no-store` — the version-key detection
    uses `parse_qs` at parser step 0.5 (errata E3), so
    `%76ersion=abc` and other percent-encoded key spellings are
    caught even when the path itself fails to parse. `/file`
    error paths ALWAYS emit a JSON envelope via
    `_send_json_error`; `/raw` error paths use the
    self-contained `_raw_error_direct` (no `send_error`
    delegation).
  Pinned by `tests/test_dashboard_ui/test_content_transport_slice1.py`
  (Slice 1 unit) plus Slice 2/3 HTTP integration tests.

- **! Shipped-template surfaces reference governed-repo paths only.**
  Any file under `src/gator_command/templates/gator-starter/` that
  lands in a fleet repo — README, HTML template bodies, procedures,
  scaffolding comments — MUST reference paths that exist in a
  gatorized repo (`.gator/procedures/…`, `.gator/blueprints/…`,
  `.gator/charters/…`). Source-tree paths (`contracts/schemas/…`,
  `src/gator_command/…`, `pytest contracts/compatibility/…`) don't
  exist in fleet repos and are dead links at the point of use. The
  ONE accepted exception is descriptive-not-prescriptive framing:
  the source-tree path may be NAMED as context ("the canonical
  contract lives in the Gator source tree at `X` and is not shipped
  here") but never as a clickable link or "go here" pointer.
  Reviewed twice in the Release A whiteboard cycle (`af6163d` +
  round-2 follow-up): round 1 caught the procedure references, round
  2 caught three README links + two template `<body>` sections that
  render into every published artifact. The higher-severity class is
  template body text — it becomes part of every newly-authored
  artifact unless the author manually rewrites it.

## Files → functions

| File | Key symbols | Reads | Writes |
|---|---|---|---|
| `contracts/compatibility/conftest.py` | `schemas_dir`, `fixtures_dir`, `reference_dir` fixtures | filesystem paths | nothing |
| `contracts/compatibility/_helpers.py` | `parse_frontmatter(md_text) → (dict, str)` | nothing | nothing |
| `contracts/compatibility/test_snippet_schema.py` | `test_schema_is_itself_valid`, `test_valid_snippet_passes`, `test_missing_required_fails`, `test_wrong_schema_tag_fails`, `test_live_repo_snippets_conform` | schema JSON, fixtures, live `.gator/session-snippets/*.json` | nothing |
| `contracts/compatibility/test_policy_pin.py` | `test_schema_is_itself_valid`, `test_schema_identifies_itself_as_v1`, `test_schema_is_additive_friendly`, `test_valid_pin_passes`, `test_empty_policies_array_is_legal`, `test_bad_hash_format_fails`, `test_missing_policies_fails`, `test_live_repo_pin_conforms` (skips pre-first-pull) | schema JSON, fixtures, live `.gator/policy-pin.json` | nothing |
| `contracts/compatibility/test_runtime_pin.py` | `test_schema_is_itself_valid`, `test_schema_identifies_itself_as_v1`, `test_schema_is_additive_friendly`, `test_valid_pin_passes`, `test_missing_manifest_fails`, `test_wrong_schema_tag_fails`, `test_malformed_manifest_digest_fails`, `test_live_repo_pin_conforms` (skips pre-Phase-1; no date-grandfathering — new artifact class, every instance postdates the contract) | schema JSON, fixtures, live `.gator/runtime-pin.json` | nothing |
| `contracts/compatibility/test_preferences_schema.py` | `test_schema_is_itself_valid`, `test_schema_identifies_itself_as_v1`, `test_schema_is_additive_friendly`, `test_hooks_section_is_reserved_stub` (forward-compat pin for the hook-mode follow-on plan), `test_valid_preferences_pass`, `test_wrong_schema_tag_fails`, `test_missing_schema_fails`, `test_python_section_optional`, `test_hooks_section_only_is_legal` (forward-compat), `test_unknown_top_level_section_tolerated`, `test_python_source_enum_enforced`, `test_updated_at_pattern_enforced`, `test_live_machine_preferences_conforms` (skips when `~/.gator/preferences.json` absent — the default state) | schema JSON, fixtures, live `~/.gator/preferences.json` | nothing |
| `contracts/compatibility/test_blueprint_html_schema.py` | `TestBlueprintHtmlSchemaConformance` (schema tag, required `<meta>` block, legal doc-class, legal status, ISO-8601 `updated-at`, no `==TODO==` placeholders survive to `.gator/blueprints/`), `TestBlueprintHtmlSelfContained` (no external stylesheets, no external scripts), `TestBlueprintHtmlDiscovery::test_gator_source_repo_ships_charter_map` (skips on non-source repos), `TestBlueprintHtmlScaffoldingExclusion` (scaffolding-exclusion contract: `_template.html` + `_template-narrative.html` land at `.gator/blueprints/` on v2 repos as `USER_VISIBLE_SCAFFOLDING` and carry `==TODO==` placeholders by design; `SCAFFOLDING_FILENAMES` filters them from `_discover_blueprints()` so fleet-repo compat runs skip cleanly instead of failing on template placeholders). Walks `.gator/blueprints/*.html` only — vault artifacts NOT schema-gated (D6, r4-r5 pin) | schema markdown, live `.gator/blueprints/*.html` | nothing |
| `contracts/compatibility/test_summary_schema.py` | parametrized `test_commit_summary_frontmatter`, `test_commit_summary_body_sections`, `test_live_commit_summaries_conform`, `test_session_summary_frontmatter`, `test_session_summary_body_sections`, `test_live_session_summaries_conform`, spec-present checks | spec + fixture files, live `.gator/sessions/*commit*.md` and `.gator/sessions/*.md` with `schema: gator-session-summary-v1` | nothing |
| `contracts/compatibility/test_enterprise_marker.py` | marker validity + `_is_enterprise_active` reference impl + fail-closed tests | schema JSON, fixtures, `tmp_path` | temp `.gator/enterprise.json` |
| `contracts/compatibility/test_hook_modes.py` | `test_gator_enforce_uses_canonical_enum`, `test_pre_commit_hook_validates_against_canonical_enum`, `test_default_config_stub_uses_strict` | shipped script sources | nothing |
| `contracts/compatibility/test_gator_layout.py` | imports `gatorize.action_install_gator` via `importlib` and runs into `tmp_path`; asserts layout marker, stubs, `.includes/`, machine-id KV format. **Runtime-split Phase 4 (2026-08-19)**: `scripts` removed from `REQUIRED_DIRS_INCLUDES`; now asserts the Phase-4 shape — `.includes/scripts/` ABSENT on fresh installs + `.gator/runtime-pin.json` present, schema-tagged `gator-runtime-pin-v1`, with a non-empty wheel-sourced manifest. **Cumberland fresh-install pin (Codex enforcer 2026-09-13 F2)**: after `action_install_gator()`, asserts the master lands at `.gator/.includes/reference-notes/cumberland-html-document-template.html` AND NOT at the flat `.gator/reference-notes/` (the latter would be the incomplete-migration `mixed` shape). Proves the plan-only routing in `test_cumberland_propagation.py` actually executes end-to-end. | `src/gator_command/scripts/gatorize.py`, `tmp_path` | tmp `.gator/` tree |
| `contracts/compatibility/test_cumberland_visual_invariants.py` (Codex Sketch 2 Slice 4, 2026-09-13, extended across enforcer rounds 1-11 through 2026-09-14; **closed round-12 on 2026-09-14 via pivot to a bounded positive-policy validator plus a pinned Content-Security-Policy `<meta>` in both templates**. The round-1..11 blacklist scanners — `_HTMLResourceScanner`, `_ExecutableScriptScanner`, WHATWG meta-refresh parser, srcset parser, CSS hex-escape decoder, active-data-document guard, and their 12 meta-pins — were DELETED. Module dropped from 2304 → 937 lines (−1367 net) per Codex's "material net reduction" stop criterion.) | Visual invariants + bounded self-containment. Visual-invariant coverage (unchanged): palette tokens, callout/pill/status-badge variants, typography (justified body + tracking + selective overrides), components (`.figure`, `.diagram-node.purple`, `.steps`, `pre code` reset, `.toc`, `.table-wrap`), body scaffolding examples. Palette (13 hex-exact tokens + 6 light-alpha washes, parametrized); callouts (default + 5 variants each with background + border-left + label color, plus `.callout.data` pinned to purple specifically); pills (6 variants); status badges (default + 3); typography (h1 `1.85rem` + `-0.01em` tracking; body `p` justified + `hyphens: auto`; subtitle same; selective left-align override for `.figure .caption` + `footer.doc-foot p` + `.toc p`); components (`.figure` block, `.diagram-node.purple`, `.steps` with 4 counter variants, `pre code` reset, `.toc`); delimiter contract (BEGIN/END markers must be inside the `<style>` block); body scaffolding examples (master body carries one visible example of every callout variant + `.figure` + `.diagram` + `.steps` + a colored table + `.table-wrap` on the sample table). **Bounded self-containment guarantee (round-12 closure)** — Codex's round-12 whiteboard replaced eleven rounds of parser-based blacklist scanners with a small positive-policy validator plus a pinned CSP `<meta>` in both templates. **The scoped claim** (round-13 F1 refined): "The two checked-in Cumberland templates contain only approved passive HTML, carry the pinned CSP that denies external resource loading, and produce no non-template network requests during Chromium's initial load." The round-12 draft said "use no external resource references"; Codex round-13 flagged that as inconsistent with the enforcement split — Layer 1 is HTML-only after round-13 F2 and does not scan CSS content, so a template carrying `background-image: image-set("https://…")` inside `<style>` would pass all three layers (Layer 1 doesn't inspect CSS, Layer 2's CSP blocks the browser fetch, Layer 3 observes no completion) while the source-text sentence remained false. The refined sentence describes what the layers actually enforce. The guarantee does NOT extend to arbitrary user-edited HTML, to every encoded/malformed browser input, or to intervals beyond Chromium's initial load — those confinements require runtime enforcement, not repository tests. **Three-layer defense**, independent and cumulative, none of them "definitive" alone: (1) `_validate_cumberland_document` — HTMLParser walk enforcing `_ALLOWED_TAGS` (26 tags: document skeleton + semantic sections + text + lists + tables + `<a>` + used SVG subset) and per-tag `_ATTR_ALLOWLIST` merged with `_GLOBAL_ATTRS`; `<a href>` values constrained to fragment-only; `<meta http-equiv>` constrained to `content-security-policy` (refresh forbidden); every `on*=` event handler flagged as its own kind; parse errors surface as `parse-error` findings (fail closed). Findings are `(kind, detail, lineno)` tuples so failure messages localize. **Layer 1 scope after round-13 F2 closure**: HTML capabilities only. CSS content inside `<style>` blocks is NOT scanned here — Chromium recognizes CSS reference shapes (uppercase `@IMPORT`, `image-set("…")`, CSS-escaped `\75rl(...)`) that a source-text scanner would need a full CSS tokenizer to match; delegating CSS to Layer 2 is the cleaner closure than maintaining a CSS parser at Layer 1. (2) Pinned CSP `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'; img-src 'none'; font-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">` in both master and narrative. CSP validation runs through `_find_csp_status`, the same HTMLParser walk that enforces Layer 1 — records every ACTIVE `<meta http-equiv="Content-Security-Policy">` with position (in-head, before-title, before-style) and content. Round-13 F1 replaced the earlier raw-substring `text.find(_PINNED_CSP_META)` which was fooled by a commented-out `<!-- <meta ...> -->`: HTMLParser routes comment content to `handle_comment`, so the inert form now counts as MISSING. Verdicts: `ok`, `missing`, `duplicate`, `csp-outside-head`, `csp-after-title`, `csp-after-style`, `csp-content-mismatch`, `parse-error`. (3) Chromium initial-load network smoke test in the companion module (see below) plus a parametrized CSP-blocks-forbidden-CSS-shapes test that executes the Layer 2 boundary against the exact CSS shapes Codex round-13 F2 reproduced against Chromium. **Test surface after closure**: `test_master_passes_positive_policy` + `test_narrative_passes_positive_policy` (both templates) + `test_positive_policy_accepts_minimal_allowed_document` (positive control) + `test_positive_policy_rejects_forbidden_class` parametrized over 27 forbidden-HTML-class fixtures (script / iframe / iframe-with-srcdoc / iframe-src-data-html / frame / object / embed / base / form / input / button / meta-refresh labeled + unlabeled / on-* / external-a-href / javascript-a-href / data-a-href / protocol-relative-a-href / img / svg-script / svg-use-xlink / link / style-attr / video / audio) + `test_csp_status_rejects_commented_out_meta` (round-13 F1 meta-pin: commented-out CSP, duplicate CSP, CSP-after-title, weakened CSP content — all rejected). **What the closure buys** (Codex's stop criterion): rejecting the enclosing tag makes every parser-detail variant moot — `iframe[srcdoc]` recursion, `data:text/html` MIME parsing, entity-encoded `javascript:` schemes, WHATWG meta-refresh grammar, CSS hex escapes, srcset comma handling all disappear because their containing capability is refused at the tag boundary. Round-13 F2 further clarified that CSS content is Layer 2's concern, executed by the browser-side test in the companion module rather than by Layer 1 source-text scans. | live `templates/…/cumberland-html-document-template.html`, `.gator/blueprints/_template-narrative.html` | nothing |
| `contracts/compatibility/test_cumberland_computed_style.py` (Codex enforcer F2 + F4, 2026-09-13; browser-level smoke test added 2026-09-14 round-8; route-filter tightened round-9; "definitive" wording narrowed round-10; **round-12 closure**: this module now owns Layer 3 of the bounded self-containment guarantee — Chromium initial-load network smoke test + **round-13 F2 addition**: parametrized CSP-blocks-forbidden-CSS-shapes test executing the Layer 2 boundary against uppercase `@IMPORT` / `image-set("…")` / CSS-escaped `\75rl(...)` and two baseline lowercase shapes) | 17 Playwright pins. **Narrow (375×667) — parametrized over master + narrative**: `documentElement.scrollWidth <= innerWidth` (F2 overflow safety net); EVERY `<table>` has a `.table-wrap` ancestor (universal, not existential); any oversized `.table-wrap` has `overflow-x: auto` computed AND actually scrolls. **Wide (1440×900) — master only**: h1 `fontSize == '29.6px'`; body padding `32px 20px` + max-width `1120px`; header border-bottom `3px solid rgb(25, 174, 184)` (teal); section > p `text-align == 'justify'`. **Initial-load network smoke test** — parametrized over both templates; `page.route("**/*", …)` intercepts every request and aborts anything not equal to the exact top-level template URL (sibling `file://` URLs treated as external too). Zero non-template requests must be recorded during initial load. Scoped claim: "no non-template network requests during Chromium's initial load" — NOT "no possible future request" and NOT "definitive on its own". **CSP-blocks-forbidden-CSS-shapes test** (round-13 F2, hardened round-14) — parametrized over five CSS shapes (`@import`, `@IMPORT`, `url()`, `image-set("…")`, `\75rl(...)`). Each fixture combines the pinned CSP (imported from the shared `_helpers.PINNED_CSP_CONTENT` — round-14 F2 replaced the duplicated `_PINNED_CSP_FOR_FIXTURES` constant so the fixture policy and the template policy cannot drift) with the forbidden CSS shape. A `securitypolicyviolation` listener installed via `page.add_init_script` BEFORE navigation captures every violation; each fixture asserts (a) Chromium fired an SPV event citing the expected directive (`style-src-elem` for `@import`, `img-src` for `url()`/`image-set`/escaped) and a blocked URI under `cdn.example`, AND (b) zero external requests completed via the routed fetch path. The SPV assertion preserves the LIVENESS signal — the round-13 form checked only (b), which cannot distinguish "CSP blocked a live request" from "the CSS fixture was ignored"; the round-14 form fails immediately if the fixture ever goes inert. Layer 1 does NOT flag these shapes after the round-12 closure — CSS content is out of Layer 1's scope; the boundary is executed at Layer 2 here. Computed-style values are browser-normalized numeric/string tokens — NOT pixel snapshots. | live `templates/…/cumberland-html-document-template.html`, `.gator/blueprints/_template-narrative.html` via file:// | nothing |
| `contracts/compatibility/test_cumberland_propagation.py` (Codex enforcer F4, 2026-09-13; CI-topology-corrected 2026-09-13 F1 round-3 re-review) | 2 pins covering the delivery seams that fit the fast compatibility matrix (no `build` package required): (1) Master exists at canonical shipped path under `templates/gator-starter/reference-notes/`. (2) `gator-update.plan_updates` — invoked in an isolated tmp_path v2 layout via `importlib.util` — produces a plan tuple `(add, source, dest)` whose dest lands at `.gator/.includes/reference-notes/cumberland-html-document-template.html`. **Actual wheel-content pins live in `tests/test_packaging.py::TestWheelBuildAndContents`** (the ONLY CI job that installs `build` and runs that suite) — the compatibility matrix does not install `build`, so wheel-building fixtures would silently skip here on the primary matrix AND never collect on the packaging matrix. **Fresh-gatorize-installs-master lives in `test_gator_layout.py::test_gatorize_install_produces_required_layout`** which reuses the existing install fixture. Skips gracefully when `gator-update.py` cannot be loaded. | live `templates/…/cumberland-html-document-template.html`, `gator-update.py`, `tmp_path` v2 seed | nothing |
| `contracts/compatibility/test_cumberland_narrative_style_parity.py` (Codex Sketch 2 Slice 3, 2026-09-12; extended by 2026-09-13 enforcer F3) | 10 pins across four axes: (1) parametrized marker-existence pin over all four Cumberland copies (master shipped-source, master `.gator/.includes/` dogfood mirror, narrative Blueprint shipped-source, narrative Blueprint `.gator/blueprints/` scaffolding-root); (2) mirror-pair byte-equality for master source↔mirror and narrative source↔mirror; (3) shared-region byte-equality between master and narrative on both the source pair AND the mirror pair; (4) Slice-2 source↔dogfood byte-equality for the constitution and `authoring-html-artifacts.md` procedure (both edited in Slice 2, both mirrored). Compact-diff failure message points at the first divergent line. This test OWNS Cumberland + Slice-2 mirror parity directly — the earlier claim that `tests/test_template_sync.py` supplied transitive coverage was false (that test covers `gator-update.py` sync only). | live `templates/…/cumberland-html-document-template.html`, `.gator/.includes/reference-notes/cumberland-html-document-template.html`, `templates/…/blueprints/_template-narrative.html`, `.gator/blueprints/_template-narrative.html`, both constitution copies, both authoring-procedure copies | nothing |

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
