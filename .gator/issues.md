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
