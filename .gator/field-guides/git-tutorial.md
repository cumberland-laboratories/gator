---
generated: 2026-06-06
generator: field-guide-gen-v1
type: pi-tutorial
language: git
source-charters: [scripts-cross-cutting, scripts-core-library, scripts-fleet-intelligence, scripts-repo-lifecycle]
patterns: git-patterns.md
---

# Git Tutorial — Gator Patterns and Strategic Features

This tutorial covers two things: the Git patterns this repo uses right now (grounded in the actual scripts), and the Git features underlying Gator's Phase 5 roadmap. The first section is how the codebase works today. The second is what those features do and why they matter for governance infrastructure.

---

## Part 1 — Patterns in Use Today

### git() Return Contract

**Charter connection**: scripts-core-library — `git()` function, `git()` Return Contract TRIPWIRE in scripts-cross-cutting

```python
# From gator_core.py
def git(*args, cwd=None):
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        return result.stdout.strip(), result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return "", False
```

**Why it matters**: The tuple return — `(stdout, success)` — forces callers to handle both failure modes: git failing entirely (`success=False`) and git succeeding but returning nothing (`success=True`, empty `stdout`). Both happen. A script that only checks `ok` will silently treat an empty git log output (no commits on that branch) as a valid result and propagate None into the report. The governance telemetry depends on this distinction being caught at every call site.

**What to watch for**: Any new git consumer that does `out, ok = git(...)` and then uses `out` without checking `if not out` first.

---

### Structured log --format with Pipe Separator

**Charter connection**: scripts-fleet-intelligence — `get_latest_trailers()`, `git_log_last_commit()`

```python
# From gator-fleet-report.py
log_line, ok = git(
    "log", "-1", "--format=%h|%s|%cr|%ci", "dev",
    cwd=repo_path
)
parts = log_line.split("|", 3)
# parts = [short_hash, subject, relative_time, iso_datetime]
```

**Why it matters**: `git log --format=` with pipe separators lets you pull structured data from git history in one subprocess call instead of many. The `%h` (short hash), `%s` (subject), `%cr` (relative time like "3 hours ago"), and `%ci` (ISO 8601 datetime) are the standard governance display fields. The `split("|", 3)` limit is intentional — commit subjects can contain pipes, and the limit prevents the subject field from being split.

**What to watch for**: The format specifier string is positional, not labeled — if you add or remove a field, you must update both the format string and the split/index logic together.

---

### %(trailers) — Governance Metadata from Commit History

**Charter connection**: scripts-fleet-intelligence — `get_latest_trailers()`, `git_log_trailers()`

```python
# From gator-fleet-report.py
raw, ok = git("log", "-1", "--format=%(trailers)", "dev", cwd=repo_path)
trailers = {}
for line in raw.splitlines():
    if ": " in line:
        key, value = line.split(": ", 1)
        trailers[key.strip()] = value.strip()
```

```python
# For a specific key only — from git log on the governance trail
git log dev..HEAD \
  --format='%(trailers:key=Gator-Change-Type,valueonly)'
```

**Why it matters**: Git trailers are key-value pairs appended to commit messages after a blank line, following the same format as email headers (`Key: Value`). Git has native support for parsing them — `%(trailers)` returns all trailers, `%(trailers:key=X,valueonly)` returns just the value for key X. Gator uses trailers as the primary governance metadata transport: `Gator-Change-Type`, `Gator-Significance`, `Gator-Charter-Changed`, `Gator-Override`. These travel with every commit, are queryable across the fleet via git log, and never require a database.

**What to watch for**: The fleet-report tries `dev` first and falls back to HEAD — `git log -1 --format=%(trailers) dev`. This is because governance trailers are written on the active development branch. A repo that only pushes to `main` may have trailers on `main`, not `dev`.

---

### git describe — Version Resolution from History

**Charter connection**: scripts-core-library — `get_version()`

```python
# From gator_core.py — resolution order
result = subprocess.run(
    ["git", "describe", "--tags", "--long"],
    capture_output=True, text=True, cwd=cwd, timeout=10,
)
# Falls back to: VERSION file → git rev-parse HEAD → "dev"
```

**Why it matters**: `git describe --tags --long` returns a string like `v1.0.0-3-gabcdef1` — tag name, commits since tag, and short hash. This is the canonical version for a git-tracked project. The `--long` flag returns the format consistently even when you're exactly on a tag. The fallback chain exists because deployed repos may be shallow clones or may not have the full tag history.

**What to watch for**: The `--long` flag matters. Without it, `git describe` returns just the tag name when HEAD is exactly tagged, which changes the output format and breaks string parsing.

---

### git status --porcelain

**Charter connection**: scripts-fleet-intelligence — `get_working_tree_status()`

```python
# From gator-fleet-report.py
status, ok = git("status", "--porcelain", cwd=repo_path)
is_clean = not bool(status)  # empty = clean
```

**Why it matters**: `--porcelain` gives machine-stable output — one line per changed file, same format regardless of git version or locale. Empty string means clean working tree. The format is not going to change between git versions the way the human-readable `git status` output might. For governance reporting, "is this repo's working tree clean?" is a meaningful signal — uncommitted changes in a governed repo may mean there's work in progress that hasn't gone through the charter-alongside-code gate yet.

---

### Bare Clone + --git-dir= for Remote Fleet Reads

**Charter connection**: scripts-core-library — `ensure_cache()`, `gator_remote.py`

```python
# From gator_remote.py — create/update a bare clone cache
subprocess.run(
    ["git", "clone", "--bare", remote_url, str(cache_path)],
    capture_output=True, text=True, timeout=120,
)
# Update existing bare clone
subprocess.run(
    ["git", f"--git-dir={cache_path}", "fetch", "origin", "--prune"],
    ...
)
# All reads against the bare clone use --git-dir=
subprocess.run(
    ["git", f"--git-dir={cache_path}"] + list(args), ...
)
```

**Why it matters**: A bare clone (`--bare`) contains the git object store without a working tree. It's significantly smaller than a full clone and is what git servers store internally. For remote fleet scanning, this is the key primitive: you can `git clone --bare` once, then `fetch` incrementally to update it, and read any file or log from any ref without ever checking out code. The `--git-dir=` flag tells git where the object store is when there's no working tree to discover it from.

**What to watch for**: Bare clones from `git clone --bare` store refs as `refs/heads/main`. After `git fetch origin`, they also have `refs/remotes/origin/main`. Both forms need to be tried when resolving which ref to read.

---

### git show {ref}:{filepath} — Single-File Remote Read

**Charter connection**: scripts-core-library — `git_show()` in `gator_remote.py`

```python
# From gator_remote.py
def git_show(cache_path, ref, filepath):
    content, ok = _git_bare(
        "show", f"{ref}:{filepath}", git_dir=cache_path
    )
    return content if ok else None

# Reading a governance file without any checkout
mission = git_show(cache_path, "origin/main", ".gator/mission.md")
charter = git_show(cache_path, "origin/main", ".gator/charters/auth.md")
```

**Why it matters**: `git show {ref}:{path}` reads a file at a specific commit or branch without touching the working tree. This is the thin-fetch model's core read primitive. For fleet reporting, it means you can read any `.gator/` governance file from any registered repo without cloning it fully. The JPMorgan problem: an enterprise eng manager with 50 repos cannot clone them all. `git show` against a bare clone cache solves this.

---

### git ls-tree — Remote Directory Listing

**Charter connection**: scripts-core-library — `git_ls_tree()` in `gator_remote.py`

```python
# From gator_remote.py
out, ok = _git_bare(
    "ls-tree", "--name-only", ref, ".gator/charters/",
    git_dir=cache_path
)
filenames = out.splitlines() if ok else []
```

**Why it matters**: `git ls-tree --name-only {ref} {dir}/` lists the files in a directory at a given ref — the remote equivalent of `os.listdir()`. Combined with `git show`, this is how fleet scanning reads charter files from remote repos: list what's there, then read each one. The trailing `/` on the directory path is required — without it, git ls-tree treats the path as a file.

---

### rev-parse --verify for Ref Existence

**Charter connection**: scripts-core-library — `_resolve_ref()` in `gator_remote.py`

```python
# From gator_remote.py — ordered ref fallback
for ref in ["origin/main", "origin/master", "origin/dev",
            "main", "master", "dev", "HEAD"]:
    _, ok = _git_bare("rev-parse", "--verify", ref, git_dir=cache_path)
    if ok:
        return ref
```

**Why it matters**: `git rev-parse --verify {ref}` exits 0 if the ref exists and resolves to a commit, exits 1 otherwise. It's the safe way to probe whether a ref exists before reading against it. The ordered fallback is important because fleet repos may use any of `main`, `master`, or `dev` as their primary branch. The `origin/` prefix forms are populated after a fetch; the bare forms may exist from the initial clone. Both must be tried.

---

## Part 2 — Strategic Git Features (Phase 5 Roadmap)

These features are not yet in use in this codebase. They underlie the Phase 5 infrastructure items in the roadmap. Understanding them is useful for knowing what the build toward "deep Git-native governance" actually involves.

→ [Strategic artifact](../artifacts/2026-06-06-git-native-gator-leverage.md)

---

### git notes — Attaching Metadata Without Changing Commits

`git notes` lets you attach arbitrary text to a commit after the fact, without changing the commit hash. Notes are stored in `refs/notes/commits` and can be pushed/fetched separately from the commit history.

```bash
# Attach a governance annotation to a commit
git notes add -m "enforcer-review: PASS, 3 warnings" abc1234

# Read the note
git log --notes abc1234

# Push notes to remote (not automatic — must be explicit)
git push origin refs/notes/commits
```

**Why it matters for Gator**: Notes could carry machine-generated review summaries, enforcer findings, or governance annotations without altering the commit record. A commit hash is tamper-evident — if you attach governance metadata inside the commit, you change the hash. Notes let you add metadata after the fact while keeping the commit hash stable. The tradeoff: notes don't travel by default (they require an explicit push/fetch refspec) and aren't visible in standard `git log` without `--notes`. Primary use case: auxiliary machine data, not primary audit evidence.

---

### Signed Tags and Commits — Governance Provenance

```bash
# Create a signed governance release tag
git tag -s v1.2.0-governance -m "Governance release: updated hooks + org-policy"

# Verify
git tag -v v1.2.0-governance

# Signed commit (requires GPG or SSH signing key configured)
git commit -S -m "Approve override: reason on record"
```

**Why it matters for Gator**: Signed tags are how you prove "this governance release was authorized by a specific identity." For enterprise buyers, the governance trail question is not just "what changed" but "who authorized it?" A signed tag on a governance release gives cryptographic proof of authorization — the kind of evidence that satisfies an auditor or a board. The tradeoff: requires signing infrastructure (GPG or SSH keys) which Gator currently avoids mandating. The roadmap item (Phase 5 #43) is optional/additive — never a hard requirement.

---

### git worktree — Multiple Working Trees from One Repo

```bash
# Create a worktree for a planner agent on its own branch
git worktree add ../planner-work feature/refactor-plan

# Create a read-only worktree for the enforcer
git worktree add --detach ../enforcer-view main

# List active worktrees
git worktree list

# Remove when done
git worktree remove ../planner-work
```

**Why it matters for Gator**: A worktree gives a second (or third) working directory from the same git object store, each on its own branch, without needing to clone. For multi-agent pipelines, this is cleaner than "open a different terminal on the same checkout" — each agent has its own scope, its own branch, and can't accidentally read each other's in-progress state. The enforcer can be given a read-only detached worktree on `main`; the implementer works in a feature-branch worktree. This is Phase 5 #42 — worktree conventions for multi-agent work.

---

### git bundle — Offline/Air-Gapped Governance Packages

```bash
# Bundle a governance release for offline distribution
git bundle create governance-v1.2.0.bundle main dev v1.2.0-governance

# Verify the bundle
git bundle verify governance-v1.2.0.bundle

# Apply in an air-gapped environment
git fetch governance-v1.2.0.bundle refs/heads/main:refs/remotes/origin/main
```

**Why it matters for Gator**: A bundle is a single portable file containing git objects and refs — a self-contained snapshot of some or all of a repo's history. For air-gapped enterprise environments (finance, defense, regulated industries), you cannot pull from a remote git host. A governance release bundle lets a security team vet and deliver a governance update via their own transfer mechanism (USB, internal file share, secure email). This is Phase 5 — compact governance bundles. The content of the bundle is: changed templates, hooks, constitution sections, migration notes.

---

### Custom Refs — Governance State Machine

```bash
# Write governance state into a custom ref namespace
git update-ref refs/gator/governance-release refs/tags/v1.2.0-governance
git update-ref refs/gator/fleet/repo-name/applied-release abc1234

# Read it back
git rev-parse refs/gator/governance-release

# Push the custom refs to remote
git push origin 'refs/gator/*:refs/gator/*'
```

**Why it matters for Gator**: Git's ref namespace is open — anything under `refs/` is valid. Most tools use `refs/heads/` and `refs/tags/`, but you can create any namespace you want. `refs/gator/` could store: the currently applied governance release for each repo, pending update intents, rollout state, enforcer review pointers. This is the "refs as control plane" item (Phase 5 #45) — using git's distributed object model to store governance state transitions, not just code history. Each fleet repo could carry its own governance state in its own ref namespace, queryable via `git ls-remote` without a central database.

---

### Server-Side Hooks — Closing the Local-Only Gap

```bash
# Server-side hooks live in the bare repo on the git server
# (GitHub: via Actions or Rulesets; GitLab: server hooks; self-hosted: hooks/ dir)

# pre-receive hook (runs on the server before accepting a push)
#!/bin/bash
while read oldrev newrev refname; do
    # Check that every commit in this push has Gator trailers
    git log --format="%(trailers:key=Gator-Change-Type,valueonly)" \
        "$oldrev..$newrev" | grep -q . || exit 1
done
```

**Why it matters for Gator**: Gator's pre-commit hook runs locally and can be bypassed with `--no-verify`. Server-side hooks run on the git host and cannot be bypassed by the committer — a push is rejected if the hook fails. For enterprise governance, this is the trust ceiling: local hooks provide fast feedback and honest agents; server-side hooks provide the guarantee that even a `--no-verify` bypass doesn't land on the protected branch. Phase 5 #44 — "close loopholes in the current local-only model." GitHub's branch protection rules and required status checks are the most accessible entry point; full server-side hooks require a self-hosted git server.
