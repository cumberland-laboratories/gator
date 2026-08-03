# Release and Deploy

The end-to-end procedure for cutting a Gator release from the monorepo. **Read every step of the "Checklist" section before starting a release** — several of the steps guard against real failures we've hit.

## When to use

Any time shipping code changes that should reach `pipx install gator-command` users. Not for internal-only work (roadmap edits, inbox captures, charter refactors that don't change shipped code) — those can just land on `dev` and fast-forward `main` without a version bump or release.

## Model overview

Three GitHub Actions workflows, one PyPI upload path, one GitHub Release. Manual dispatch on the promote step (human approves before production PyPI accepts the wheel).

```
  dev commits ─push─▶ source-ci.yml (test matrix + wheel-install smoke)
      │
      │ ff-merge when source-ci green
      ▼
  main commits ─push─▶ source-ci.yml
      │
      │ tag vX.Y.Z-rcN
      ▼
  release-candidate.yml ─▶ TestPyPI publish (OIDC) ─▶ Ubuntu + Windows smoke
      │
      │ human dispatches promote-to-pypi.yml with (rc_version, run_id, "publish")
      ▼
  approval gate at pypi-production environment
      │
      │ human approves
      ▼
  promote-to-pypi.yml ─▶ production PyPI publish (OIDC, same wheel) ─▶ fresh-env smoke
      │
      │ gh release create
      ▼
  GitHub Release published
```

Wheel is built **exactly once** — the artifact from `release-candidate.yml` is what `promote-to-pypi.yml` re-uploads to production PyPI. No rebuild in the chain.

## Prerequisites (one-time setup — already done for this repo)

- **PyPI Trusted Publisher** registered at https://pypi.org/manage/account/publishing/. Values: Owner `cumberland-laboratories`, Repository `gator`, Workflow name `promote-to-pypi.yml`, Environment name `pypi-production`.
- **TestPyPI Trusted Publisher** registered at https://test.pypi.org/manage/account/publishing/. Values: Owner `cumberland-laboratories`, Repository `gator`, Workflow name `release-candidate.yml`, Environment name `pypi-test`. Separate account, separate registration.
- **GitHub environments**:
  - `pypi-test` — no protection rules (RC cadence must be automated)
  - `pypi-production` — required reviewer = the human doing releases (approval gate)
- **Repo variables**: `RELEASE_PIPELINE_ENABLED = true` (whole-pipeline kill switch). `DEPLOY_PUBLIC_ENABLED` intentionally unset — that gated a legacy deploy-to-separate-public-repo step that the monorepo cutover retired.
- **GitHub Actions permissions**: "Allow actions created by GitHub" + "Allow actions by Marketplace verified creators" (or "Allow all"). Verified creators is required for `pypa/gh-action-pypi-publish`.
- **Local**: `gh` CLI authenticated to `cumberland-laboratories` account. Python 3.9+ with `build` and `twine` (only needed for local test builds; release path uses CI).

## Branch discipline

Per `CONTRIBUTING.md` `## Branching`:

- Work on `dev`. Push freely.
- **Every commit on `main` MUST have a green `source-ci` run.** `main` is the release-anchor branch.
- When `dev` is green, fast-forward `main` to `dev`:
  ```bash
  git checkout main
  git merge --ff-only dev
  git push origin main
  ```
  If the fast-forward fails, someone else moved `main` — rebase `dev` on top first (`git checkout dev && git rebase main`), retry the merge.
- **Release tags are cut from `main` only.** Never tag a commit that hasn't gone through the ff-merge.

## The 2.5.2 partial-commit incident (hard-won lesson)

**Every `git add` of more than 2-3 files MUST be followed by `git diff --cached --name-only` before `git commit`.** Eyeball the list. Compare to what you intended to stage.

Why: v2.5.2 shipped from a commit that silently dropped ~10 intended files during a Windows Git Bash trailing-backslash `git add \` continuation. Only ~3 of the ~13 intended files staged. The commit succeeded, CI passed (didn't catch the missing content), a release cut, PyPI shipped a wheel that didn't match its CHANGELOG. Discovered on the next session by diffing working tree against HEAD.

The fix: pause between `git add` and `git commit`. Look at what's staged. Confirm the list. **Only then commit.**

## Checklist (do these in order for every release)

### 1. Prep on `dev`

- [ ] All intended code changes committed to `dev`
- [ ] All tests added/updated for new code
- [ ] All charter updates staged for touched code files (INDEX.md rows tell you which charters are required for which paths)
- [ ] `source-ci.yml` green on `dev` (check https://github.com/cumberland-laboratories/gator/actions?query=branch%3Adev)
- [ ] Local test run: `python -m pytest tests/ contracts/compatibility/ -q` passes

### 2. Version bump commit

- [ ] `pyproject.toml` `version = "X.Y.Z"` (semantic: patch for bug fixes, minor for features, major for breaking changes)
- [ ] `VERSION` file (root) matches (must stay byte-consistent — enforced by `scripts-core-library.md` charter tripwire)
- [ ] `CHANGELOG.md` — add new `## [X.Y.Z] — YYYY-MM-DD` section above the previous entry. Categorize changes under `### Added / Changed / Fixed / Deprecated / Removed / Security`. Reference test file names and charter tripwires so future readers can find the pins.
- [ ] `.gator/commit_draft.md` populated with `change-type: release` (from the schema-legal enum: `feature | fix | refactor | docs | test | release | maintenance | review | governance | ""`)
- [ ] Charter mention: touching `VERSION` triggers the pre-commit `charter-alongside-code` rule. The `scripts-core-library.md` tripwire on `get_version()` already documents the sync obligation — a small note-update there (e.g. "current: X.Y.Z") satisfies the rule.
- [ ] `git add pyproject.toml VERSION CHANGELOG.md .gator/charters/scripts-core-library.md`
- [ ] **`git diff --cached --name-only` — verify staging matches intent**
- [ ] `git commit -m "Bump to X.Y.Z"`
- [ ] `git push origin dev`
- [ ] Wait for `source-ci` green on `dev`

### 3. Fast-forward to main

- [ ] `git checkout main`
- [ ] `git merge --ff-only dev`
- [ ] `git push origin main`
- [ ] Wait for `source-ci` green on `main` (usually green immediately since dev was green)

### 4. Tag RC (fires the release-candidate pipeline)

- [ ] `git tag -a vX.Y.Z-rc1 -m "Release candidate 1 for vX.Y.Z"`
- [ ] `git push origin vX.Y.Z-rc1`
- [ ] `release-candidate.yml` auto-fires. Watch: `gh run watch $(gh run list --repo cumberland-laboratories/gator --workflow release-candidate.yml --limit 1 --json databaseId --jq '.[0].databaseId') --repo cumberland-laboratories/gator --exit-status`
- [ ] Expected jobs (all green): `RC tag validation + kill switch`, `build wheel once`, `publish to TestPyPI (OIDC trusted publisher)`, `fresh-env install from TestPyPI + CLI smoke (ubuntu-latest)`, `fresh-env install from TestPyPI + CLI smoke (windows-latest)`. `deploy candidate as PR into public gator repo` should show as `skipped` (the deploy step is a retired-flow stub, gated by absent `DEPLOY_PUBLIC_ENABLED`).
- [ ] **Save the run ID** — you'll need it as `workflow_b_run_id` for the promote step.

**Handling TestPyPI filename-permanence** (see #4 in `.gator/issues.md`): if the RC fails and you need to iterate, you must **bump the base version** for the next RC (e.g. `X.Y.Z-rc1` fails → next RC is `X.Y.(Z+1)-rc1`, NOT `X.Y.Z-rc2`). TestPyPI never lets you re-upload a filename, and `release-candidate.yml` doesn't inject the RC suffix into the wheel version — both `-rc1` and `-rc2` would build `gator_command-X.Y.Z-py3-none-any.whl` and the second upload gets `400 File already exists`. Version churn cost per failed RC: one patch version.

### 5. Dispatch promote-to-pypi

Two paths — either works. Both require your approval at the environment gate.

**Via `gh` CLI**:
```bash
gh workflow run promote-to-pypi.yml \
  --repo cumberland-laboratories/gator \
  --ref main \
  -f rc_version=vX.Y.Z-rc1 \
  -f workflow_b_run_id=<RUN_ID_FROM_STEP_4> \
  -f confirm=publish
```

**Via GitHub UI**:
1. https://github.com/cumberland-laboratories/gator/actions/workflows/promote-to-pypi.yml
2. Run workflow → main
3. Inputs: `rc_version=vX.Y.Z-rc1`, `workflow_b_run_id=<run ID>`, `confirm=publish`
4. Run workflow

- [ ] Watch: `gh run watch $(gh run list --repo cumberland-laboratories/gator --workflow promote-to-pypi.yml --limit 1 --json databaseId --jq '.[0].databaseId') --repo cumberland-laboratories/gator`
- [ ] Workflow queues the `publish to production PyPI` job → hits `pypi-production` env approval gate
- [ ] **Approve the gate** — GitHub notifies you (email + web). Approve.
- [ ] Publish job runs → wheel goes to PyPI via OIDC (no static token)
- [ ] Post-publish smoke job runs

### 6. Handle post-publish smoke failure (expected the first try)

PyPI CDN needs ~30–60 seconds after upload for the simple index to reflect the new version. The post-publish smoke job runs immediately after upload — it usually fails on the first attempt with:

```
ERROR: Could not find a version that satisfies the requirement gator-command==X.Y.Z (from versions: ..., X.Y.(Z-1))
```

Recovery: **wait for propagation, then rerun the failed job**:
```bash
# Verify propagation
python -c "import urllib.request, json; d = json.loads(urllib.request.urlopen('https://pypi.org/pypi/gator-command/json').read()); print('Latest:', d['info']['version'])"
# When it shows X.Y.Z, rerun:
gh run rerun <PROMOTE_RUN_ID> --failed --repo cumberland-laboratories/gator
```

(Tracked as inbox item to auto-handle in the workflow.)

- [ ] Second smoke run passes → promote workflow fully green

### 7. Tag final version + GitHub Release

- [ ] `git tag -a vX.Y.Z -m "vX.Y.Z — one-line summary"` (at the same commit the RC pointed at)
- [ ] `git push origin vX.Y.Z`
- [ ] Draft release notes as `.tmp/vX.Y.Z-release-notes.md` (gitignored). Include user-facing framing, migration notes, `pipx install` line, link to CHANGELOG section.
- [ ] `gh release create vX.Y.Z --repo cumberland-laboratories/gator --title "vX.Y.Z — <summary>" --notes-file .tmp/vX.Y.Z-release-notes.md --latest`
- [ ] Confirm at https://github.com/cumberland-laboratories/gator/releases/latest

### 8. Post-release verification

- [ ] `pipx upgrade gator-command` on a machine with the previous version — confirm it goes to X.Y.Z
- [ ] `gator --version` reports X.Y.Z
- [ ] `.gator/roadmap.md` updated with the new row in the Done table (this can be a small follow-on commit on `dev` — doesn't need to block the release)
- [ ] `.gator/issues.md` — mark any issues this release resolved as `Resolved`

## Recovery: wheel doesn't match CHANGELOG (like 2.5.2 → 2.5.3)

If post-release you discover the shipped wheel is missing content the CHANGELOG claims (staging silent-drop, workflow bug, etc.):

1. **Do not try to overwrite the version on PyPI** — PyPI's no-filename-reuse policy blocks it even after "yank." The bad version stays bad forever.
2. **Bump patch version.** Ship the missing content in `X.Y.(Z+1)`.
3. **Honest CHANGELOG entry** for the recovery release: name the missed prior release, describe what was missing, describe what this release adds. See the `[2.5.3]` entry as the reference example.
4. **Yank the bad version** on PyPI (Settings → Releases → yank) so `pip install gator-command` skips it by default while remaining installable with an explicit `==X.Y.Z`.

Cost is minor (one skipped version number). Credibility cost of releasing an overpromising wheel without a follow-up is higher.

## Hard promises

- **Wheel built exactly once** per release, in `release-candidate.yml::build-candidate`. `promote-to-pypi.yml` fetches that artifact by name and re-uploads it — no rebuild.
- **No static PyPI tokens** anywhere in the repo. Both TestPyPI and PyPI use OIDC trusted publishing. If setup breaks, the fix is reconfigure trusted publisher, not add a token.
- **`RELEASE_PIPELINE_ENABLED` AND environment approval both required.** Removing either is a governance violation.
- **`main` is release-anchor.** Every release tag points at a commit whose `source-ci` was green.
- **No manual `twine upload`** — the pipeline is the only publish path. The one-off local `python -m build` is fine for testing wheel shape but never for release.

## Connections

- `.gator/charters/release-pipeline.md` — full workflow charter (job graph, kill-switch semantics, artifact-name contract)
- `.gator/procedures/gator-loop-protocol.md` — governance-loop reference; loops are unrelated to release cadence
- `.gator/issues.md` #4 — RC-suffix injection missing in `release-candidate.yml` (drives the "bump base version per failed RC" workaround)
- `.gator/issues.md` #5 — Node.js 20 deprecation warnings on `actions/*` v4/v5 (needs `actions/checkout@v5`, `actions/setup-python@v6`, etc. bump before GitHub's deadline)
- `.gator/inbox.md` — "Promote workflow smoke test needs a PyPI-propagation wait" (the fix for step 6 above)
- `CONTRIBUTING.md ## Branching` — the dev→main flow this procedure assumes
- `CHANGELOG.md` — release history + the `[2.5.3]` recovery-release example
