# Issues

Active bugs, blockers, and known fragilities.

**Status key**: Open · Working · Resolved

---

## #1. Gator-Charter-Changed trailer misses charter updates

**Status**: Open
**Discovered**: 2026-08-02 (post-monorepo-cutover fixes commit `5dcdbdd`)
**Severity**: Minor (cosmetic — trailer value only; hook still blocks on missing charters correctly)

The `Gator-Charter-Changed:` trailer emitted by
`gator-pre-commit.py --phase trailers` reported `no` on commit `5dcdbdd`
even though the commit modified two charters
(`.gator/charters/scripts-cross-cutting.md` and
`.gator/charters/scripts-repo-lifecycle.md`). Expected: `yes` (or a
non-`no` sentinel indicating charter files were part of the diff).

The pre-commit hard-rule `charter-alongside-code` fires correctly for
code changes without charter updates — that path is unaffected. Only
the trailer emitter's classification is off. Likely: the classification
in `phase_trailers` uses a different staged-files reader or filter than
`classify_staged_files` in `validate_hard_rules`, or the charter path
predicate looks for a directory that excludes `.gator/charters/` on v2
layout.

Fix path (small): trace the trailer's staged-files walk in
`gator-pre-commit.py::phase_trailers` and confirm it uses the same
`classify_staged_files()` helper as the validate phase, or reconcile
the classification logic between the two phases.

Regression pin needed after fix: a test that commits a change touching
both a code file and a `.gator/charters/*.md` file, then asserts the
`Gator-Charter-Changed` trailer value is not `no`.

---

## #2. Dashboard renders empty `gator-command/` sidebar section in monorepo mode

**Status**: Resolved (false alarm — not an actual bug)
**Discovered**: 2026-08-02
**Resolved**: 2026-08-02 (dashboard registry fix)

The "empty section" the Architect observed was because the Dashboard's `gator` registry entry pointed at `C:\Users\curator\code2\gator-test\gator` (an old test repo from 2026-06-19), not the actual monorepo at `C:\Users\curator\code2\gator`. The test repo does have `gator-command/` content that legitimately renders. When the registry was fixed to point at the real monorepo, no phantom section appears — the backend guard on `gc_dir.is_dir()` at `dashboard/gator-dashboard.py:405-419` correctly skips the scan, `gcFiles` is empty, and the frontend renders nothing.

No code change needed. Filed the fix suggestion for `dashboard/views/repo.js:390-391` (guard on `gcFiles.length > 0`) is a nice-to-have defensive tweak but not a bug in isolation.

---

## #3. Dashboard swallows update errors as a bare "!"

**Status**: Open
**Discovered**: 2026-08-02 (trying to run Dashboard Update on the mixed-layout monorepo)
**Severity**: Moderate (user gets no signal, has to drop to CLI to see the real error)

When `gator update` fails on a Dashboard-triggered Update, the row's
activity column renders a bare "!" with no error text. The real
error message (`"Layout is mixed -- run 'gator update --migrate-layout'
to repair before updating."` in the case that surfaced this) never
reaches the UI.

Underlying `/api/repo/<name>/update` endpoint has the message in the
subprocess stderr/stdout; the Dashboard frontend just doesn't render
it. The Update button ends up worse than useless in an error state —
users have to `cd` into the repo and `gator update` from the terminal
to see what happened.

Fix path: return the last N lines of stderr/stdout in the endpoint's
error JSON, render them under the "!" pill or in a tooltip/modal.

---

## #4. `release-candidate.yml` doesn't inject RC suffix into wheel version

**Status**: Open
**Discovered**: 2026-08-02 (during v2.5.0-rc1/rc2 iteration during monorepo cutover)
**Severity**: Moderate (blocks RC iteration; forces version-number churn)

`release-candidate.yml` (`build wheel once` step) uses
`python -m build --wheel` against the repo as-is — the wheel's version
comes from `pyproject.toml`'s `version` field verbatim. There is no
RC-suffix injection.

Consequence: every `vX.Y.Z-rcN` tag builds a wheel named
`gator_command-X.Y.Z-py3-none-any.whl` — no RC suffix. Once
uploaded to TestPyPI, TestPyPI's permanent no-filename-reuse policy
prevents a subsequent `-rcN+1` from uploading (blocked as "400 File
already exists"). Every RC iteration therefore requires bumping the
BASE version (2.5.0 → 2.5.1) to unblock the pipeline, burning a
version number per RC attempt.

Two fix paths:

- **Sed-inject `pyproject.toml` version at build time** — the RC
  workflow could read the tag (e.g. `v2.5.3-rc1`), extract the RC
  suffix, and rewrite `version = "2.5.3rc1"` before invoking `build`.
  Small workflow change, no shipping-code impact.
- **`setuptools-scm`** — derives version directly from git tag,
  no `pyproject.toml` `version` field maintained by hand. Cleaner
  long-term but larger refactor + affects every version-reading
  code path.

Recommend the sed approach for now.

---

## #5. Node.js 20 deprecation warnings on `actions/*` v4/v5

**Status**: Open
**Discovered**: 2026-08-02 (annotations on every source-ci and release-candidate run)
**Severity**: Low → escalates (deadline-driven; GitHub will force-fail eventually)

Every workflow run emits deprecation annotations for
`actions/checkout@v4`, `actions/setup-python@v5`,
`actions/upload-artifact@v4`, `actions/download-artifact@v4`. GitHub
Actions runners are forcing these onto Node.js 24 today; a hard
switch-off of Node 20 is coming (see
`https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/`).

Fix: bump each to the version that ships with a Node 24 target. Trivial
edits across `.github/workflows/*.yml` — verify each still works.

---

## #6. `migrate_layout()` Step 5 doesn't handle directory conflicts

**Status**: Resolved (2026-08-03, commit `5453f8b`)
**Discovered**: 2026-08-03 (running `gator update --migrate-layout` on the fleet repo `code/donoriq`)
**Severity**: Moderate (blocks `gator update` on any repo that accumulated non-scaffolding subdirs under `.gator/scripts/`; requires manual cleanup)

**Resolution**: A1 of the 2026-08-03 update-and-begin-session bugs fix set. `migrate_layout()`'s Step 5 loop now handles both-directories-exist: `__pycache__` and `hooks` (known-safe legacy residue) are `shutil.rmtree`'d unconditionally; everything else goes through `_merge_dir_files_only()` — recursive files-only merge, dest wins on collision, non-file/non-dir entries and non-empty leftover subdirs logged into `report["conflicts"]`. A2 adds `_enumerate_mixed_residue()` so residual mixed-layout cases get a concrete blocking-paths list. Regression pins: `tests/test_layout.py::TestMigration::test_shipped_dir_pycache_conflict_removed` and `test_shipped_dir_unknown_dir_conflict_merges`. Fleet repos that accumulated `.gator/scripts/__pycache__/` or `.gator/scripts/hooks/` residue can now run `gator update --migrate-layout` and converge without manual pre-cleanup.

Original report retained below for context:


Sibling to the file-conflict bug that v2.5.3 fixed. In `gator-update.py::migrate_layout()` Step 5 (SHIPPED_DIRECTORIES merge), when a shipped directory (`scripts/`, `reference-notes/`) exists at BOTH `.gator/<dir>/` and `.gator/.includes/<dir>/`, the merge loop handles FILES correctly (v2.5.3 fix — moves non-duplicates, removes src on file-name conflicts) but **skips DIRECTORY conflicts entirely**:

```python
elif f.is_dir() and not dest_f.exists():
    shutil.move(str(f), str(dest_f))
    report["moved"].append(f"{dname}/{f.name}/")
```

There's no `else` branch for `f.is_dir() and dest_f.exists()`. If `.gator/scripts/__pycache__/` exists at src AND `.gator/.includes/scripts/__pycache__/` exists at dest, both are left in place. Then `src_dir.rmdir()` fails because src still has content, layout re-detects as `mixed`, migration reports "Result: mixed (migration incomplete — check conflicts)" and never converges.

**Common triggers** (any fleet repo that was gatorized under an older Gator and then had scripts touched):

- `.gator/scripts/__pycache__/` — Python bytecode from running any script under that directory. Regenerated on every Python invocation.
- `.gator/scripts/hooks/` — legacy pre-monorepo installation location for git hook wrappers. Now regenerated to `.git/hooks/` (or `.git/gator-hooks/` on Windows) by `install_git_hooks()` (Step 5a of the migration). The `.gator/scripts/hooks/` copies are dead weight after migration.

**Manual workaround** (what we did for donoriq):

```bash
rm -rf .gator/scripts/__pycache__ .gator/scripts/hooks
# `.gator/scripts/` is now empty (or only user-authored scripts remain)
gator update  # layout is now v2, no --migrate-layout needed
```

**Fix path**:

Extend Step 5's iteration to add an `else` branch for the both-directories-exist case:

- Src subdir name is `__pycache__` → `shutil.rmtree(f)` unconditionally. Bytecode is safe to delete.
- Src subdir name is `hooks` → `shutil.rmtree(f)`. Hooks are regenerated by `install_git_hooks()` in Step 5a to `.git/hooks/`, not to `.includes/scripts/hooks/`. The `.gator/scripts/hooks/` copies are legacy.
- Other subdirs → policy decision. Options: (a) recursive merge (files from src → dest if not present, else remove src file; then rmdir src if empty); (b) log conflict + preserve src (safe but leaves mixed); (c) refuse migration with explicit conflict report. Suggest (a) with a warning naming the moved files.

Regression pin needed: a test that sets up `.gator/scripts/__pycache__/gator_core.cpython-313.pyc` AND `.gator/scripts/hooks/pre-commit` at both `.gator/scripts/` and `.gator/.includes/scripts/`, runs migrate_layout, and asserts layout converges to v2 with the root subdirs gone.

Documentation follow-up: `.gator/procedures/release-and-deploy.md` Step 4 references "cross-platform test matrix" for pre-migration state — should call out the `__pycache__`/`hooks` cleanup as a common pre-migration action on fleet repos.

---
