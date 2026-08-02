# Gator Contracts Layer

This directory is the **executable contract surface** between the base
Gator install and the optional Enterprise capability. It exists because
markdown-only contracts drift; every high-risk boundary in this layer has
a companion pytest check that CI can enforce.

## Structure

```
contracts/
  schemas/
    gator-session-snippet-v2.json    JSON Schema — session snippet emission (shared)
    enterprise-config.json           JSON Schema — .gator/enterprise.json marker
    gator-session-summary-v1.md      Markdown spec — vendor-session summary frontmatter
    gator-commit-summary-v1.md       Markdown spec — commit summary frontmatter + sections
  reference/
    hook-mode-vocabulary.md          strict / warn / off — canonical enum
    machine-identity.md              ~/.gator/machine-id file format
    gator-directory-layout.md        Post-gatorize .gator/ tree expectations
    presence-detection.md            How each half detects the other
  compatibility/
    conftest.py                      Shared fixtures for the pytest suite
    fixtures/                        Valid + invalid samples used by checks
    test_snippet_schema.py           Validate snippets against the JSON Schema
    test_summary_schema.py           Validate commit + session summary markdown
    test_enterprise_marker.py        Marker schema + presence-detection contract
    test_hook_modes.py               Both products accept the same enum values
    test_gator_layout.py             Post-gatorize layout matches the spec
```

## What contracts are for

The monorepo convergence plan collapses base Gator and Enterprise into a
single wheel, but they still cross a real boundary at runtime — the base
hook code emits snippets that the Enterprise pipeline consumes; the
Enterprise marker flips optional behaviors on; both halves agree on
`.gator/` layout, hook-mode vocabulary, and machine identity. This layer
is the codified handshake.

Contracts are **not**:

- documentation of internal implementation details,
- a place to describe features that are still being designed,
- or a substitute for module charters (see `gator-command/charters/`).

Contracts describe the **stable, cross-half surfaces** whose shape must
not change without a versioned schema bump.

## Running the checks

```bash
pip install -r contracts/requirements.txt pytest
python -m pytest contracts/compatibility -v
```

`jsonschema` is only needed for the two JSON-Schema-backed tests
(`test_snippet_schema.py`, `test_enterprise_marker.py`), which use
`pytest.importorskip` to degrade cleanly on a bare interpreter. That
soft-skip is dev-local convenience — **CI MUST install
`contracts/requirements.txt` explicitly** so those tests actually run.
A green CI run without `jsonschema` installed would be a false pass.

## Adding a contract

1. Write the schema or spec under `schemas/` (JSON Schema for
   structured data, markdown-with-frontmatter-spec for humans+machines).
2. Add fixtures under `compatibility/fixtures/` — one valid, at least
   one invalid.
3. Add or extend a pytest file under `compatibility/` that loads the
   schema and validates the fixtures.
4. If the contract is greenfield (no code yet emits or reads it), mark
   it as such in the spec header. Downstream code must be written to
   satisfy the contract, not the other way around.

## Versioning

Every schema carries an explicit version tag in its identifier
(`gator-session-snippet-v2`, `gator-session-summary-v1`, etc.). A
breaking change is a new version, not an in-place edit. Old and new may
coexist for a release cycle.
