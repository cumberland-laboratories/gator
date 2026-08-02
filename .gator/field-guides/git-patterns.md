---
generated: 2026-06-06
generator: field-guide-gen-v1
type: agent-patterns
language: git
source-charters: [scripts-cross-cutting, scripts-core-library, scripts-fleet-intelligence, scripts-repo-lifecycle]
source-file-count: 8
pattern-count: 10
tutorial: git-tutorial.md
---

# Git Patterns

### git() Return Contract
Files: gator_core.py (definition), gator-fleet-report.py, gator-drift.py, gator-fleet-intel.py
Returns `(stdout: str, success: bool)`. Never raises. Always check both — `success=True` with empty `stdout` is a valid non-result, not a silent success.
! Callers that only check `ok` will treat empty output as a good result. Both must be checked. This is the most common git consumer bug in this codebase.

### Structured log --format with Pipe Separator
Files: gator_core.py, gator-fleet-report.py, gator_remote.py
Use `--format=%h|%s|%cr|%ci` to extract hash, subject, relative date, ISO date in one call. Split on `|` with a count limit: `split("|", 3)`. The pipe char is safe — it doesn't appear in git format specifiers.

### %(trailers) Extraction
Files: gator-fleet-report.py, gator_remote.py
`--format=%(trailers)` returns all trailers as `Key: Value\n` lines. Parse with `line.split(":", 1)` and strip both sides. Iterate until a blank line — that marks the end of one commit's trailers when requesting multiple commits.
! The fleet-report tries `dev` first, then HEAD as fallback: `git log -1 --format=%(trailers) dev`. Order matters — always prefer the branch that carries governance trailers.

### %(trailers:key=X,valueonly) for Specific Keys
Files: gator-pre-commit.py, gator-fleet-report.py
To extract one trailer by name: `--format=%(trailers:key=Gator-Change-Type,valueonly)`. Returns just the value, no key prefix. Use this for display and analytics queries.

### git describe Resolution Chain
Files: gator_core.py
Version resolution order: `git describe --tags --long` → VERSION file → `git rev-parse HEAD` → "dev". Deployed repos without full tag history fall back to the VERSION file. Never hardcode version strings.

### git status --porcelain for Clean/Dirty
Files: gator-fleet-report.py
`git status --porcelain` returns empty string for a clean working tree, otherwise one line per changed file. Empty string = clean. Check `bool(output)` not the success flag.

### Bare Clone + --git-dir= for Remote Reads
Files: gator_remote.py
Bare clones (`git clone --bare`) let you read any file or log from a remote repo without a working tree. All commands against a bare clone use `git --git-dir=/path/to/cache.git <command>`. Never use `cwd=` with a bare repo — use `--git-dir=`.

### git show {ref}:{filepath} for Single-File Remote Read
Files: gator_remote.py
Read one file from a remote ref without checking out anything: `git --git-dir=... show {ref}:{filepath}`. Returns file contents or fails cleanly. This is the thin-fetch model's core primitive.

### git ls-tree for Remote Directory Listing
Files: gator_remote.py
`git --git-dir=... ls-tree --name-only {ref} .gator/charters/` returns filenames in a remote directory. Combine with `git show` to read each file. Together these two commands replace a full checkout for governance state reads.

### rev-parse --verify for Ref Existence
Files: gator_remote.py
Check whether a ref exists before using it: `git --git-dir=... rev-parse --verify origin/main`. Try ordered fallbacks: `origin/main`, `origin/master`, `origin/dev`, then bare-native `main`, `master`, `dev`, then `HEAD`. Bare clones after `git fetch` have both `refs/remotes/origin/main` and `refs/heads/main`.
