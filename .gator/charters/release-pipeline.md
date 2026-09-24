# Charter: Release Pipeline

**Covers**: `.github/workflows/**`, `scripts/release-individual.sh`, `scripts/test-install-cycle.sh`, `scripts/monorepo-bootstrap.py`, `scripts/monorepo-validate.py`

## Owns

- Source validation on pushes and pull requests.
- Release-candidate build and TestPyPI validation.
- Approval-gated promotion of the already-built candidate to PyPI.
- Release scripts used to exercise source and installed-wheel behavior.

## Does Not Own

- Package contents and CLI behavior; see domain charters and `pyproject.toml`.
- Contract definitions; see [`contracts.md`](contracts.md).
- Enterprise deployment operations.

## Workflow A: Source CI

File: `.github/workflows/source-ci.yml`

Runs fast platform/Python lanes plus packaging and compatibility work required for ordinary changes.

! Source CI has no publication side effects.
! Every required lane must be green to merge; do not hide a required suite behind an uncollected path or missing optional dependency.
! Python versions remain consistent with `pyproject.toml` support.
! Jobs that execute contract tests install `contracts/requirements.txt`.
! Workflow syntax/action policy is validated by a real workflow linter and focused tests, not YAML parsing alone.
! Third-party actions use reviewed immutable pins or the repository's explicit major-version policy; permissions remain least-privilege per job.

## Workflow B: Release Candidate

File: `.github/workflows/release-candidate.yml`

Builds the candidate once, validates the artifact, publishes to TestPyPI through its dedicated trusted publisher, and prepares downstream release inputs.

! The wheel is built exactly once in the build job. All validation and publication consume that artifact.
! Artifact names and expected paths are a contract with the promotion workflow.
! TestPyPI and PyPI use separate OIDC trusted-publisher registrations.
! Matrix jobs bind `runs-on` to the matrix OS.
! Disabled or deferred deployment steps are visibly stubbed; no step claims a deployment it did not perform.

## Workflow C: Promote to PyPI

File: `.github/workflows/promote-to-pypi.yml`

Promotes a previously validated release-candidate artifact after independent environment approval.

! Promotion never rebuilds the package.
! Artifact identity and approval are independent gates before publication.
! PyPI publication uses OIDC trusted publishing; long-lived API tokens are not stored.
! `id-token: write` is job-local to the publication job.

## Release Scripts

File: `scripts/release-individual.sh`
File: `scripts/test-install-cycle.sh`
File: `scripts/monorepo-bootstrap.py`
File: `scripts/monorepo-validate.py`

Exercise versioning, source-tree integrity, wheel installation, and end-to-end CLI behavior outside workflow YAML.

! Release scripts fail on partial validation and surface the exact command that failed.
! Temporary install-cycle state is isolated from developer machine state.
! Source validation and installed-wheel validation are complementary; neither substitutes for the other.

## Before Changing This Module

- Confirm permissions, secrets/OIDC environment, concurrency, and artifact lineage.
- Verify action runtime support and immutable pin policy.
- Lint workflow YAML and run focused workflow-policy tests.
- Exercise the local release/install script path where feasible.
- Keep enablement runbooks and historical rollout notes outside this charter.

## Connections

-> [Contracts](contracts.md) - compatibility matrix inputs
-> [Cross-Cutting](scripts-cross-cutting.md) - package, license, and CLI surface
-> [Enterprise Dispatcher](scripts-enterprise.md) - installed-wheel optional capability
