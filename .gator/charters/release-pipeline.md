---
charter: release-pipeline
scope: .github/workflows/ — automated CI + release pipeline (Workflows A, B, C all shipped; B and C wired but disabled pending operator setup)
last-verified: 2026-08-01
---

# Charter: Release Pipeline

## Purpose

The GitHub Actions workflows under `.github/workflows/` implement the
three-workflow release topology from
`../artifacts/2026-07-27-public-release-pipeline-design.md`:

- **Workflow A — Source CI** (shipped 3b-1)
- **Workflow C — Promote to PyPI** (shipped 3b-2, wired but disabled)
- **Workflow B — Release Candidate** (shipped 3b-3, wired but disabled; deploy step behind a second `DEPLOY_PUBLIC_ENABLED` sub-gate pending cutover)

## Files

| File | Role | Status |
|---|---|---|
| `.github/workflows/source-ci.yml` | Workflow A: pytest + contracts on push/PR | Shipped 3b-1 |
| `.github/workflows/release-candidate.yml` | Workflow B: RC-tag → wheel build + TestPyPI + public deploy PR | Shipped 3b-3, wired but disabled (deploy step STUBs pending cutover) |
| `.github/workflows/promote-to-pypi.yml` | Workflow C: approval-gated PyPI publish (OIDC trusted publisher) | Shipped 3b-2, wired but disabled |

## Workflow A — Source CI

Runs on every push to `main` and every PR into `main`. No publication
side effects; read-only correctness gate.

Two lanes:

- **fast**: matrix `[ubuntu-latest, windows-latest] × [python 3.9, 3.13]`
  runs `tests/` + `contracts/compatibility/` with
  `--ignore=tests/test_packaging.py`. Windows is in the matrix because
  several v2.4.x hotfixes were Windows-specific (cp1252 decoding, hook
  wrapper generation) and the platform is a first-class dev target.
  Python 3.9 pins the minimum from `pyproject.toml:requires-python`;
  Python 3.13 pins the current maximum from the same file's classifiers.
- **packaging**: single job (`ubuntu-latest × python 3.13`) runs
  `tests/test_packaging.py` — the slow suite that builds a wheel and
  installs into a fresh venv per class. Kept out of the fast matrix
  because each class-scoped fixture rebuilds the wheel and creates a
  venv, and multiplying that by four matrix cells wastes ~3 minutes per
  run for no additional signal.

## Invariants (`!`)

- **! No publication side effects in Workflow A.** Source CI MUST NOT
  publish to TestPyPI, PyPI, or any external registry. It MUST NOT
  push to any repo. It MUST NOT open PRs. It MUST NOT deploy to the
  public `gator` repo. Those responsibilities belong to Workflows B
  and C. A regression that added publication behavior to Workflow A
  would breach the release-pipeline design's "public repo deploy is a
  gate, not a side effect" principle.

- **! Both lanes must be green to merge.** The `fast` matrix (4 jobs)
  and the `packaging` job (1 job) are equally load-bearing. Branch
  protection on `main` SHOULD require both. A `fast`-only green
  represents unit-level correctness with no packaging assertion; a
  `packaging`-only green represents build correctness on one runner
  with no cross-platform assertion.

- **! Concurrency cancels prior runs on the same ref.** The
  `concurrency` block cancels in-flight runs when a new commit arrives
  on the same branch or PR. Read-only workflows can be cancelled
  freely; do not remove the cancellation policy.

- **! Python version matrix is anchored to `pyproject.toml`.**
  `requires-python = ">=3.9"` and the `Programming Language :: Python`
  classifiers define the supported range. The matrix currently pins
  the two ends (3.9, 3.13). When the range changes in `pyproject.toml`,
  update the matrix in the same commit.

- **! `contracts/requirements.txt` is installed in every job that
  runs the contracts suite.** Skipping it would silently disable the
  JSON-Schema-backed tests via `pytest.importorskip("jsonschema")`
  and produce a false green. This satisfies the "CI MUST install
  contracts/requirements.txt" invariant in `contracts.md`.

- **! Least-privilege GITHUB_TOKEN in every workflow.** Every
  workflow file MUST declare a top-level `permissions:` block that
  narrows `GITHUB_TOKEN` to the minimum scope its jobs actually need.
  Workflow A (read-only) declares `permissions: contents: read` and
  passes `persist-credentials: false` to every `actions/checkout`
  step so that credentials do not outlive the checkout in git config.
  Workflows B and C, when they land, MUST declare their own narrower
  scopes (e.g. `contents: write` for the B deploy-to-public-repo
  step, `id-token: write` for OIDC to PyPI). Never rely on the
  repository default — it can be broader than the charter intends
  and it can change out from under the workflow.

- **! Codified verification for workflow YAML uses a real linter,
  not `yaml.safe_load` alone.** PyYAML parses the unquoted GitHub
  Actions key `on:` as boolean `True` (YAML 1.1 boolean coercion),
  so `yaml.safe_load(text)['on']` fails and a naive
  "triggers wired correctly" check can silently look at nothing. Use
  `actionlint` when available, or explicitly check both `True in data`
  and `'on' in data` when using PyYAML, or preprocess by quoting the
  `on:` key. This is called out because a Codex Phase 3b-1 review
  caught a commit-draft narrative that overstated a `yaml.safe_load`
  verification; the fix is to make future verification claims
  precise about what was actually checked.

## Workflow B — Release Candidate (shipped 3b-3, wired but disabled)

Triggers on every `v*.*.*-rc*` tag push. Four sequential-with-fanout
jobs:

1. **`gate`** — validates tag pattern (belt-and-suspenders to the
   `on.push.tags` filter) + kill-switch check.
2. **`build-candidate`** — installs `build`, runs `python -m build --wheel`
   exactly once, verifies exactly one wheel produced, extracts the PEP
   440 version from the wheel filename, uploads the artifact under the
   coupling-contract name `candidate-wheel-${{ github.ref_name }}` with
   90-day retention. Emits `wheel_version` as a job output.
3. **`publish-to-testpypi`** (parallel with `deploy-to-public-gator`) —
   runs inside the `pypi-test` protected environment (no required
   reviewers — TestPyPI is validation, not production). Uses
   `pypa/gh-action-pypi-publish` with `repository-url` overridden to
   `https://test.pypi.org/legacy/`. OIDC trusted publisher, no static
   token.
4. **`smoke-test-testpypi`** — matrix (Ubuntu + Windows) fresh-venv
   install from TestPyPI using `--index-url https://test.pypi.org/simple/
   --extra-index-url https://pypi.org/simple/ --pre "gator-command==${version}"`,
   then runs `gator --version` and `gator --help`. Windows in the matrix
   because the packaging suite's Phase-3a checks proved Windows is a
   distinct install surface.
5. **`deploy-to-public-gator`** (parallel with `publish-to-testpypi`) —
   STUB pending cutover. Documents three viable deploy shapes (same-repo
   monorepo / GitHub App / PAT) so cutover work swaps the STUB for real
   deploy without redesigning the workflow.

### Invariants added by Workflow B

- **! Build the wheel exactly once, in `build-candidate`.** No other
  job in this workflow runs `python -m build` or any equivalent. All
  downstream jobs (`publish-to-testpypi`, `smoke-test-testpypi`,
  eventual `deploy-to-public-gator`) consume the artifact via
  `actions/download-artifact`. Workflow C consumes the same artifact
  from the same run. The artifact IS the release candidate; anything
  that produces a new build is a violation of the "artifact promotion,
  not rebuild-on-publish" release-pipeline design principle.

- **! Artifact-name coupling contract with Workflow C.** The upload
  step uses the exact name `candidate-wheel-${{ github.ref_name }}`
  (e.g. `candidate-wheel-v2.4.5-rc1`). Workflow C's `fetch-candidate`
  job downloads by that exact name. Renaming this artifact in isolation
  breaks the C promotion chain. Rename only via coordinated change
  across both workflows.

- **! TestPyPI OIDC is a distinct trusted-publisher registration.**
  The `pypi-test` environment maps to a separate Trusted Publisher
  registered on `test.pypi.org` (not `pypi.org`). Sharing a single
  registration for both would either fail to publish or publish to the
  wrong index. Setup requires two independent one-time configurations,
  one per index.

- **! No approval on `pypi-test`.** TestPyPI publishes are validation
  and MUST run automatically on every RC tag. Adding a required
  reviewer defeats the whole point of TestPyPI as a fast validation
  channel. Approval belongs on the `pypi-production` environment
  (Workflow C only).

- **! `deploy-to-public-gator` STUB is honest about its state.** Until
  cutover chooses a deploy shape (same-repo monorepo, GitHub App, or
  PAT), the STUB exits `78 (EX_CONFIG)` — but the whole job is gated
  behind a second flag: `vars.DEPLOY_PUBLIC_ENABLED == 'true'` in
  addition to `RELEASE_PIPELINE_ENABLED == 'true'`. Absent by default,
  so the job SKIPS rather than FAILS after the pipeline is enabled.
  This lets an enabled RC run pass cleanly on build + TestPyPI + smoke
  test alone — the operator gets a green run whose ID Workflow C's
  `fetch-candidate` can reference for promotion. When cutover work
  replaces the STUB with real deploy logic, flip `DEPLOY_PUBLIC_ENABLED`
  in the same change. Codex Phase 3b-3 review flagged the earlier
  single-gate design as one that would produce red runs on every RC
  after enable.

- **! Matrix jobs bind `runs-on` to `matrix.os`.** Any job that declares
  `strategy.matrix.os` MUST also set `runs-on: ${{ matrix.os }}` — a
  hardcoded `runs-on: ubuntu-latest` collapses every cell onto the
  same runner and gives the workflow false cross-platform coverage.
  Codex Phase 3b-3 review caught this on `smoke-test-testpypi`: the
  `[ubuntu-latest, windows-latest]` matrix was declared but the job
  hardcoded Ubuntu, so the Windows cell silently ran on Ubuntu and
  the `RUNNER_OS == 'Windows'` branch inside the smoke script never
  fired.

## Workflow C — Promote to PyPI (shipped 3b-2, wired but disabled)

Triggers on `workflow_dispatch` with three required inputs:

- `rc_version` — the tag Workflow B built (e.g. `v2.4.5-rc1`). Regex-validated as `vX.Y.Z-rcN`.
- `workflow_b_run_id` — the Actions run ID that produced the candidate artifact.
- `confirm` — must be exactly the string `publish` or the workflow refuses.

Jobs pipeline:

1. **`gate`** — verifies confirmation phrase and RC-version shape.
2. **`fetch-candidate`** — pulls the candidate wheel from Workflow B's
   uploaded artifact via `gh run download --repo ${{ github.repository }}
   --name candidate-wheel-${{ inputs.rc_version }} --dir dist/`. Job-
   scoped `permissions: contents: read, actions: read` (the `actions:
   read` scope is what `gh run download` needs). Emits the exact PEP
   440 package version parsed from the wheel filename as a job output;
   `post-verify` consumes it verbatim rather than deriving a version
   from the `rc_version` input, so the smoke test always installs
   precisely what was published. B→C artifact-name coupling contract
   is enforced by both sides using the same `${{ ...ref_name...
   }}` / `${{ ...rc_version... }}` value (they resolve to the same
   string on a tag push).
3. **`publish`** — runs inside the `pypi-production` protected
   environment (approval gate). Uses `pypa/gh-action-pypi-publish` with
   OIDC trusted publishing — no static PyPI token. Guards that
   exactly one wheel is in `dist/` before publishing.
4. **`post-verify`** — bounded poll of the PyPI JSON API for the
   just-published version (8 attempts × 15s = 120s max) BEFORE the
   install step. PyPI's upload succeeds well before its CDN populates
   all edges — pip installs typically 404 for ~30-60s after a fresh
   publish. Every v2.5.2 → v2.6.0 promote failed the immediate
   post-publish smoke on this exact race; the wait-for-CDN step (added
   2026-08-13) polls `https://pypi.org/pypi/gator-command/${version}/json`
   until visible. Then creates a fresh venv, installs the just-published
   package from production PyPI, runs `gator --version` + `gator --help`
   as a smoke check.

### Invariants added by Workflow C

- **! No rebuild. Ever.** Workflow C MUST NOT contain
  `python -m build` or any equivalent command. The wheel it publishes
  is the byte-identical artifact produced by Workflow B and validated
  by B's TestPyPI smoke tests. Rebuilding here defeats the
  release-pipeline design's "artifact promotion, not rebuild-on-publish"
  principle. Adding a build step is a governance violation.

- **! Two independent gates before publish.** Workflow C requires both
  the `RELEASE_PIPELINE_ENABLED == 'true'` repo variable (hard kill
  switch, project-owner-controlled) AND the `pypi-production` protected
  environment approval (human-in-the-loop reviewer, GitHub-native).
  Removing either without an explicit governance decision is a
  contract violation.

- **! OIDC trusted publishing only.** The `pypi-publish` step MUST NOT
  set `password` or `user` — those parameters trigger fallback to
  static-token auth and defeat the OIDC trust chain. A missing PyPI
  trusted-publisher configuration is a setup error, not a reason to
  add static tokens as a workaround. Static PyPI tokens create
  long-lived secrets that outlive their intended blast radius.

- **! OIDC id-token scope is job-local.** Only the `publish` job
  declares `permissions: id-token: write`. Other jobs stay at the
  workflow-level `contents: read` — a compromised action in a
  fetch or verify job cannot mint a PyPI publish token.

### Enabling Workflow C (one-time setup)

1. On PyPI: configure a Trusted Publisher for this repo. Owner
   `cumberland-laboratories`, workflow `promote-to-pypi.yml`,
   environment `pypi-production`. See https://docs.pypi.org/trusted-publishers/.
2. In the GitHub repo settings, create the `pypi-production`
   environment with at least one required reviewer.
3. Set the `RELEASE_PIPELINE_ENABLED` repository variable to `true`.

Workflow B is now shipped (3b-3) and its `build-candidate` job uploads
the artifact `candidate-wheel-${{ github.ref_name }}` that Workflow C's
`fetch-candidate` downloads by name. The B→C handoff works in behavior
today (not just in comments) — provided the operator supplies a valid
`workflow_b_run_id` at dispatch time.

## Called by (`←`)

- GitHub Actions runners on the `gator-command` repo — triggered by
  the events declared in each workflow's `on:` block.
- Branch protection on `main` (when configured) — depends on Workflow
  A's `fast` and `packaging` jobs as required status checks.

## Calls out (`→`)

- `python -m pytest tests contracts/compatibility` — Workflow A fast
  lane; contract described by `pytest.ini::testpaths` and
  `contracts/README.md`.
- `python -m pytest tests/test_packaging.py` — Workflow A packaging
  lane; contract described by `tests/test_packaging.py` (see
  `TestWheelBuildAndContents` and `TestInstalledArtifact`).
- `contracts/requirements.txt` — installed in the fast lane to enable
  JSON-Schema-backed contract checks.
- Future: TestPyPI + PyPI publish endpoints (Workflows B and C).

## Connections

→ Plan artifact:
  `../artifacts/2026-07-27-public-release-pipeline-design.md` — the
  release-pipeline design that specifies the three-workflow topology
  and the fail-closed promotion boundary.
→ Plan artifact:
  `../artifacts/2026-07-21-monorepo-convergence-implementation-plan.md`
  Phase 3 — packaging + release control.
→ [Contracts](contracts.md) — CI-side invariant that
  `contracts/requirements.txt` MUST be installed in any job running the
  contracts suite; the reciprocal of the contracts-side invariant.
→ [Cross-Cutting](scripts-cross-cutting.md) — packaging test surface
  (`tests/test_packaging.py`) that Workflow A's packaging lane
  exercises end-to-end.
→ Procedure:
  `../procedures/release-and-deploy.md` — the release procedure the
  workflows automate; the procedure notes CI green as a precondition.
