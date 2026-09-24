# Charter: Compatibility Contracts

**Covers**: `contracts/**`

## Owns

- Versioned schemas and reference vocabularies shared across Gator surfaces.
- Positive, negative, and live compatibility tests for those contracts.
- Cumberland HTML template parity, bounded passive-content policy, propagation, and browser-computed visual invariants.

## Does Not Own

- Producer or consumer implementations; see their domain charters.
- General unit tests whose assertions are not a released compatibility boundary.
- Release workflow orchestration; see [`release-pipeline.md`](release-pipeline.md).

---

### schema documents
File: contracts/schemas/*
Define versioned wire/file formats for snippets, summaries, runtime pins, policy pins, preferences, Enterprise markers, and Blueprint HTML metadata.
<- product writers and readers
-> compatibility tests
! Schemas are additive-friendly unless a version explicitly says otherwise. Unknown fields remain acceptable; removing/renaming required meaning requires a new version.

### reference contracts
File: contracts/reference/*
Define stable vocabularies and directory/presence semantics that are awkward to express as JSON Schema.
<- hook, layout, machine identity, and presence consumers
! Update the reference and every executable consumer/test in the same change.

### snippet, summary, pin, preference, and marker compatibility
File: contracts/compatibility/test_snippet_schema.py
File: contracts/compatibility/test_summary_schema.py
File: contracts/compatibility/test_runtime_pin.py
File: contracts/compatibility/test_policy_pin.py
File: contracts/compatibility/test_preferences_schema.py
File: contracts/compatibility/test_enterprise_marker.py
Validate schemas themselves, known-valid/invalid fixtures, and live artifacts when present.
<- Source CI
-> schemas, fixtures, repository or machine state
! A missing optional live artifact may skip its live-instance check. Missing schema/fixture files and malformed present artifacts fail closed.

### hook-mode and layout compatibility
File: contracts/compatibility/test_hook_modes.py
File: contracts/compatibility/test_gator_layout.py
Pin shared hook vocabulary and the observable result of a fresh Gator installation.
<- Source CI
-> starter templates and installer
! Fresh-layout checks validate executed installation output, not only planning constants.

### Blueprint HTML compatibility
File: contracts/compatibility/test_blueprint_html_schema.py
Validate required metadata, allowed document classes/statuses, placeholder exclusion, and self-contained shipped blueprints.
<- Source CI
-> Blueprint schema and `.gator/blueprints/*.html`
! Scaffolding templates intentionally contain placeholders and are excluded by explicit filename, not by weakening published-document validation.

### Cumberland template parity
File: contracts/compatibility/test_cumberland_narrative_style_parity.py
Pin source/dogfood mirror equality and byte-identical Cumberland style regions between the master and narrative Blueprint template.
<- Source CI
-> master/narrative templates and mirrored governance files
! The shared style region is edited once and synchronized across every asserted copy in the same commit.

### Cumberland passive-document policy
File: contracts/compatibility/test_cumberland_visual_invariants.py
Apply an allowlist-based HTML capability policy and validate the pinned CSP plus required visual vocabulary.
<- Source CI
-> Cumberland master and narrative templates
! Keep the claim bounded: shipped templates contain approved passive HTML, carry the pinned CSP, and are checked for initial-load isolation. This is not a sanitizer for arbitrary user HTML.
! HTML capability checks use a positive tag/attribute policy. CSS egress is enforced by CSP/browser tests rather than an ad-hoc CSS parser.

### Cumberland browser and propagation checks
File: contracts/compatibility/test_cumberland_computed_style.py
File: contracts/compatibility/test_cumberland_propagation.py
Pin narrow/wide layout behavior, initial-load network isolation, CSP liveness against forbidden CSS resource shapes, and correct v2 template routing.
<- Source CI browser/compatibility jobs
-> Chromium, update planner, shipped templates
! Network tests assert both a security-policy violation signal and zero completed external requests so an inert fixture cannot pass silently.
! Wheel-content checks stay in the packaging suite where build dependencies are installed; do not hide them behind skips in the fast contract matrix.

## Contract Rules

- Every contract has at least one executable positive and negative assertion.
- Contract failures are failures, not convenience skips. Skips are reserved for explicitly absent optional live state or unavailable platform tooling.
- Live-artifact grandfathering, where still required, is explicit and date/format bounded.
- Compatibility tests are a package so shared helpers and pinned constants have one import path.
- CI jobs running JSON Schema tests install `contracts/requirements.txt`.
- Security and format contracts use positive policies where possible; avoid expanding blacklist parsers round after round.

## Adding or Changing a Contract

1. Define the smallest stable schema or reference vocabulary.
2. Add valid and invalid fixtures.
3. Add executable tests for the writer/reader boundary and, where useful, a live instance.
4. Update all producers and consumers atomically.
5. Route the affected files through [`INDEX.md`](INDEX.md) and link the owning domain charter.

## Before Changing This Module

- Identify whether the change is additive or version-breaking.
- Verify CI installs every dependency needed to execute the contract.
- Run the compatibility matrix and the producer/consumer domain tests.
- Keep review chronology and pass counts in Git or artifacts, not here.

## Connections

-> [Cross-Cutting](scripts-cross-cutting.md) - shared schema/version rules
-> [Dashboard Server](scripts-dashboard.md) - content transport and CSP
-> [Dashboard UI](scripts-dashboard-ui.md) - iframe and document rendering
-> [Enterprise CLI](scripts-enterprise-cli.md) - policy/runtime artifact consumers
-> [Enterprise Server](scripts-enterprise-server.md) - wire and persistence producers
-> [Release Pipeline](release-pipeline.md) - contract execution in CI
