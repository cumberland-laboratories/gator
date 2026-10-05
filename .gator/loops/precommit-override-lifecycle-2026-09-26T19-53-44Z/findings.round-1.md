# Review: Retry-Safe Pre-Commit Override Approval — Round 1

## Executive Summary

- The revised immutable approval snapshot and supersede matrix correctly preserve authorization through a secondary fix-required block.
- Dispatcher ownership and caller-root resolution are now correctly placed and tested.
- One delivery detail remains: the plan names a mandatory dogfood `.gator/.includes/scripts/` copy, but this source checkout currently has no repo-resident pre-commit/approve runtime copy under that path.
- Resolve the delivery matrix before implementation so the new shared import is present in every runtime that can execute `gator-pre-commit.py`, without reintroducing a retired repo-runtime surface.

## Verdict

REVISE

## Findings

### Finding 1: Replace the assumed dogfood copy with a verified delivery matrix

**Severity**: Medium

**Issue**: Change 1 still says `precommit_override.py` has a dogfood copy in
`.gator/.includes/scripts/`. This source repository currently has no
repo-resident `gator-pre-commit.py` / `gator-approve.py` copy there; the
runtime-split dispatcher normally uses the installed wheel's starter-template
scripts. Adding a new source-repo dogfood copy without an identified delivery
contract risks restoring a parallel runtime, while omitting the helper from a
legacy repo copy would make its `gator-pre-commit.py` import fail.

**Required revision**: Replace the assertion with a source-of-truth matrix:
the installed-wheel template, legacy repo-runtime copies (only where the
installer/update path still ships them), and the Enterprise bundled runtime.
For each, name the installer/update synchronization mechanism and its test.
First inspect the template-copy/update manifest and existing byte-identity
tests; then list only the actual required copies. Add an install/update
regression proving any runtime that receives the changed pre-commit script
also receives `precommit_override.py`.
