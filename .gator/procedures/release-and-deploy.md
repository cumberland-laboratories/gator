# Release and Deploy

How to release changes from gator-command to the Gator public repo and PyPI.

## When to Use

Any time changes in gator-command are ready to ship — template updates, script changes, doc fixes, dashboard improvements. This is a frequent operation.

## Automated CI (Workflow A — shipped 3b-1)

`.github/workflows/source-ci.yml` runs on every push to `main` and every PR into `main`. Two lanes:

- **fast**: matrix Ubuntu + Windows × Python 3.9 + 3.13 — runs `tests/` and `contracts/compatibility/` (excludes the slow packaging suite).
- **packaging**: single job Ubuntu × Python 3.13 — runs `tests/test_packaging.py`, which builds a wheel and installs it into a fresh venv for the installed-CLI smoke tests.

**Before proceeding with a release**, confirm CI is green on `main`. Both lanes must pass — a `fast`-only green misses the packaging surface; a `packaging`-only green misses cross-platform coverage. See [`release-pipeline.md`](../charters/release-pipeline.md) for the full charter.

Workflow A is read-only: it does NOT publish, does NOT push, does NOT deploy. Publication belongs to Workflows B (release candidate — shipped 3b-3, wired but disabled) and C (PyPI promote — shipped 3b-2, wired but disabled). Until both are enabled, the manual steps below remain the current release path.

## Automated release candidate (Workflow B — shipped 3b-3, wired but disabled)

`.github/workflows/release-candidate.yml` runs on every `vX.Y.Z-rcN` tag push. It builds the wheel once, publishes to TestPyPI, runs installed-CLI smoke tests from TestPyPI on Ubuntu + Windows, and (when the STUB is filled in) opens a deploy PR against the public gator repo. The wheel it uploads becomes the immutable candidate artifact Workflow C promotes to production PyPI — no rebuild in the chain.

**One-time setup**:

1. **TestPyPI Trusted Publisher**. Register at https://test.pypi.org/manage/account/publishing/ — Owner `cumberland-laboratories`, workflow `release-candidate.yml`, environment `pypi-test`. This is a distinct registration from the production PyPI trusted publisher.
2. **`pypi-test` GitHub environment**. Create in repo Settings → Environments with **no** required reviewers — TestPyPI is validation, approval friction defeats the automated RC cadence.
3. **Kill switch**. Same `RELEASE_PIPELINE_ENABLED = true` repo variable that gates Workflow C. Setting it once enables build + TestPyPI + smoke test jobs.
4. **Deploy sub-gate — deliberately left OFF**. `DEPLOY_PUBLIC_ENABLED` repo variable is separate from the pipeline kill switch. Leave it absent (or explicitly `false`) until cutover work replaces the deploy STUB with real behavior. With the sub-gate off, the `deploy-to-public-gator` job SKIPS cleanly (not FAILS), and the enabled RC run passes green on build + TestPyPI + smoke — giving the operator a valid run ID for Workflow C promotion.

**Trigger a release candidate**:

```bash
# 1. Bump version in pyproject.toml, commit
# 2. Tag with the RC pattern
git tag v2.4.5-rc1
git push origin v2.4.5-rc1
```

Workflow B fires automatically on the tag push. Watch it in Actions. When TestPyPI publish + smoke test pass, note the run ID — that's the `workflow_b_run_id` input Workflow C needs to promote.

**Hard promises**:
- Wheel built exactly once, in `build-candidate`. No downstream job rebuilds.
- Artifact name is a contract: `candidate-wheel-${{ github.ref_name }}`. Workflow C's `fetch-candidate` depends on the exact string.
- TestPyPI OIDC is separate from production PyPI OIDC — two independent trusted-publisher registrations.
- `pypi-test` never gains a required reviewer — that would break automated RC cadence.

Until the deploy STUB is filled in, Workflow B still produces a validated TestPyPI-installable candidate — that alone is meaningful pre-production evidence.

## Automated PyPI publish (Workflow C — shipped 3b-2, wired but disabled)

`.github/workflows/promote-to-pypi.yml` implements approval-gated OIDC publish to production PyPI. Present but inert until you flip three switches:

**One-time setup** (do these once, then never again):

1. **PyPI Trusted Publisher**. Configure at https://docs.pypi.org/trusted-publishers/ — Owner `cumberland-laboratories`, workflow `promote-to-pypi.yml`, environment `pypi-production`. Removes the need for a static PyPI token secret in the repo.
2. **Protected environment**. In repo Settings → Environments, create `pypi-production` with at least one required reviewer. This is the human-in-the-loop approval gate.
3. **Kill switch**. In repo Settings → Variables, set `RELEASE_PIPELINE_ENABLED = true`. Absent or any other value = every job skips.

**When ready to promote a candidate** (assumes Workflow B has produced the artifact — B shipped in 3b-3, wired but disabled by the same `RELEASE_PIPELINE_ENABLED` flag):

1. Note the run ID of the passing Workflow B run for your RC tag.
2. Actions tab → Promote to PyPI → Run workflow.
3. Fill inputs:
   - `rc_version` — exactly the tag Workflow B built (e.g. `v2.4.5-rc1`).
   - `workflow_b_run_id` — the run ID from step 1.
   - `confirm` — type exactly `publish`.
4. Approve the deployment when the `publish` job requests it.
5. Post-verify runs automatically — check its output for the smoke-test result.

**Hard promises**:
- Workflow C never rebuilds the wheel. It publishes the byte-identical artifact from Workflow B.
- No static PyPI token exists in the repo. If setup breaks, the fix is to reconfigure the trusted publisher, not to add a token.
- Both the repo variable AND the environment approval must pass. Removing either is a governance violation.

Workflow C's `fetch-candidate` job downloads the artifact via `gh run download` against the `workflow_b_run_id` you pass in — the B→C handoff works end-to-end today. There is no manual-upload fallback path in the workflow — if a promote is needed against a wheel Workflow B did not produce (e.g. a hotfix built manually), implement the fallback as its own change (add a `wheel_url` input, download it, verify checksum) rather than bolting in an unaudited artifact.

Until the pipeline is enabled operator-side, the manual procedure below remains the current release path.

## Prerequisites

- Working tree is clean or all intended changes are committed
- Both repos are locally available:
  - `code2/gator-command` (this repo)
  - `code2/gator` (Gator public — `cumberland-laboratories/gator`)
- `~/.pypirc` configured with PyPI API token (one-time setup):
  ```ini
  [pypi]
  username = __token__
  password = pypi-<your-token>
  ```
- `build` and `twine` installed: `pip install build twine`
- `gh` CLI installed and authenticated (`gh auth status` shows the `cumberland-laboratories` account)

## Procedure

### Step 1: Update CHANGELOG.md

Add a new version section to `CHANGELOG.md` in this repo with a summary of what changed. This file is copied to the public repo during deploy.

### Step 2: Bump version

Update `pyproject.toml` with the new version number. The deploy script reads this to:
- Stamp the public README banner
- Auto-write the `VERSION` file in the public repo

### Step 3: Commit and tag

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "v1.x.y: description"
```

### Step 4: Deploy to Gator public

From the gator-command repo root:

```bash
python src/gator_command/scripts/gator-deploy.py ../gator
```

This builds `gator-engine/` (scripts, templates, tests, docs), stamps README and VERSION from `pyproject.toml`, and copies curated root files (CHANGELOG, LICENSE, etc.).

### Step 5: Commit and push Gator public

```bash
cd ../gator
git add -A
git commit -m "Deploy v1.x.y: description"
git push origin main
```

### Step 6: Build and publish to PyPI

From the gator-command repo root:

```bash
python -m build --wheel
python -m twine upload dist/gator_command-1.x.y-py3-none-any.whl
```

Twine reads the token from `~/.pypirc` automatically — no interactive prompt.

### Step 7: Push source repo

```bash
git push origin main
```

Public repo is already pushed in Step 5 — this pushes the source-repo commits (version bump, CHANGELOG entry).

### Step 8: Tag public repo and publish GitHub Release

Tag the public repo at HEAD (the deployed state):

```bash
cd ../gator
git tag v1.x.y
git push origin v1.x.y
```

Extract the CHANGELOG section for this version and publish the Release:

```bash
# Extract just this version's CHANGELOG entry
awk '/^## \[1\.x\.y\]/{flag=1;next} /^## \[/{flag=0} flag' CHANGELOG.md > /tmp/release-notes.md

# Publish
gh release create v1.x.y \
  --repo cumberland-laboratories/gator \
  --title "v1.x.y — <one-line summary>" \
  --notes-file /tmp/release-notes.md
```

Longer-form Release notes (with narrative sections, headline, migration notes) can live in `.gator/vault/YYYY-MM-DD-github-release-vX.Y.Z.md` in the source repo — pass that path to `--notes-file` instead of the auto-extracted CHANGELOG section. The vault draft never ships; only what `gh release create` reads gets published.

**Discussions integration** (optional): add `--discussion-category Announcements` to create a linked Discussion in the Announcements category. Lets people react/comment without a second post to maintain.

## Notes

- **Version is early**: bump `pyproject.toml` before deploying — the deploy script reads it for the README stamp and VERSION file. PyPI rejects duplicate versions.
- **CHANGELOG is manual**: write it before deploying. The deploy copies it to the public repo.
- **VERSION is auto-stamped**: the deploy writes VERSION from `get_source_version()` (reads pyproject.toml). The static `VERSION` file in the source repo is a fallback only.
- **Dry run**: add `--dry-run` to the deploy command to preview without writing.
- **Public repo structure**: `gator-engine/` + root files only. No `.gator/` or `gator-command/` in the public repo.
- **Public docs are curated**: only docs listed in `PUBLIC_DOCS` in `deploy_builders.py` ship to the public repo.

## Connections

-> [`gator-deploy.py`](../../src/gator_command/scripts/gator-deploy.py) — the deploy script
-> [`deploy_builders.py`](../../src/gator_command/scripts/deploy_builders.py) — build sections + PUBLIC_DOCS list
