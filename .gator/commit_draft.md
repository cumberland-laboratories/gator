---
message: "Fix cross-platform path in remove 404 test"
change-type: fix
significance: routine
decision-tags: [testing, cross-platform]
agent: claude-opus-4-6
architect:
---

# Session Change Log

- Fixed `test_remove_repo_not_found_returns_404`: the "not-here" path was
  not resolved through `Path.resolve()`, so on Linux it was treated as
  relative (non-absolute) and hit the 400 validation instead of the 404
  not-found path. Both Ubuntu CI jobs failed on this.
