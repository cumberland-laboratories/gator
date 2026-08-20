# Procedure: Gator Version Drift Across Branches — Merges, Conflicts, and Origin Skew

**Audience**: AI models working in a Gator-governed repo when Gator versions differ between branches, when a merge produces conflicts in `.gator/` files, or when origin is ahead/behind on Gator content.

**Symptom that triggers this procedure**: any of —

- `git merge` / `git rebase` / `git pull` reports conflicts in `.gator/` paths.
- Two branches in the same repo show different versions in `.gator/.gator-version`.
- `git status` after a pull shows unexpected `.gator/` changes from a teammate's `gator update`.
- You are about to merge a branch and notice the other side ran `gator update` (or gatorize) and yours did not — or vice versa.

**Short answer**: this is routine, not an emergency. Git handles the mechanics; your job is to apply the right resolution rule **per file class**, then let the installed CLI re-canonicalize shipped content with one `gator update`. Do not ask the operator which Gator version they want — the answer is always the same: **the latest installed CLI wins, applied via `gator update` after the merge**.

## 0a. Post-2.9 note (runtime split, Phase 4)

From Gator 2.9 onward, updated repos NO LONGER carry runtime scripts —
`.gator/.includes/scripts/` is removed and the committed
`.gator/runtime-pin.json` records which machine-side runtime governs the
repo. Consequences for this procedure:

- The largest Class A merge surface (the scripts tree) no longer exists
  on pinned repos — most shipped-content conflicts simply stop occurring.
- A `runtime-pin.json` conflict resolves like any Class A file: take
  either side whole, run `gator update` on the merged result, commit.
- Merging a pinned branch with a pre-2.9 branch that still carries
  scripts: resolve scripts-side conflicts with `--theirs`/`--ours`
  (either), finish the merge, run `gator update` — it re-pins and
  removes the scripts tree on the merged result.

Everything below remains correct for pre-2.9 repos and mixed merges.

## 1. The one principle that resolves most of this

Shipped Gator content is **generated, version-owned, and reproducible**. It is not source to be hand-merged — it is output that `gator update` can rewrite to canonical form at any time. Therefore a conflict in shipped content never needs a careful line-by-line merge: clear the conflict any valid way, finish the merge, run `gator update`, commit the result. The CLI is the merge tool for its own files.

User-authored knowledge is the opposite: it is real content with no generator, and it merges like any prose — carefully, preserving both sides' meaning.

Everything below is the application of that split.

## 2. File classes and their resolution rules

### Class A — shipped content (CLI-owned; never hand-merge)

**Paths**: everything under `.gator/.includes/` (v2 layout) or the shipped files at `.gator/` root on v1 layouts (constitution, shipped procedures/reference-notes/scripts, `.charterignore`); the Gator-managed blocks in entry-point files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`); `.gator/.gator-version`.

**Rule**: on conflict, take **either side whole** (`git checkout --theirs <path>` or `--ours` — it genuinely does not matter which), complete the merge, then run `gator update` on the merged branch. The update overlays every shipped file to the canonical version for the installed CLI and re-stamps `.gator-version`. If the CLI itself is older than the newer branch's content came from, run `pipx upgrade gator-command` first, then `gator update`.

**Never**: hand-merge conflict markers inside shipped files, keep a "hybrid" of two shipped versions, or edit shipped content to preserve local tweaks (local agent guidance belongs in `CLAUDE.local.md` / `AGENTS.local.md` / `GEMINI.local.md`, which are gitignored and never conflict).

### Class B — user-authored knowledge (real merges; both sides matter)

**Paths**: `.gator/mission.md`, `roadmap.md`, `inbox.md`, `patterns.md`, `charters/*.md`, `threads/`, `active-threads/`, `artifacts/`, `blueprints/`, `docs/`, user-authored procedures at `.gator/procedures/`.

**Rule**: merge like any document — preserve both sides' content, reconcile duplicates. Per-file semantics:

- **`inbox.md`** — union of open items from both sides; drop exact duplicates; if both sides edited the "where we are" block, the newer session's version wins and anything only the older side knew gets folded in.
- **`roadmap.md`** — union of rows/entries; when both sides updated the same item's status, the more-advanced status wins (Considering < Designed < Building < Done).
- **`charters/*.md`** — special: a charter must describe the **merged code**, not either branch's code. Resolve textually (union of entries), then verify the merged charter against the merged source — function entries from both sides should each still name real functions. On any doubt, run the quick check from `procedures/charter-alignment.md`.
- **`mission.md` / `patterns.md` / threads / artifacts** — ordinary prose merges; conflicts here mean both branches did real thinking, so keep both and reconcile meaning, not just lines.

### Class C — generated governance residue (usually cannot conflict)

- **`.gator/session-snippets/*.json`** — one file per commit with unique names; a merge unions the files and true conflicts are near-impossible. Keep **all** snippet files from both sides — they are the evidence trail. Never delete a snippet to "clean up" a merge.
- **`commit_draft.md`, `whiteboard.md`, `status.json`** — gitignored since v2.1.0 and should never appear in a merge. If a legacy repo still tracks them: take either side; the hooks reset them on the next commit anyway.

### Class D — hooks

Git hooks live in `.git/` (untracked) and are machine-local. After any merge that changed Gator versions, the next `gator init` refreshes them automatically. If hook behavior seems stale post-merge, run `gator init` — do not copy hook files across branches by hand.

## 3. Scenario walkthroughs

### 3a. Merging a branch that ran `gator update` into one that didn't (or vice versa)

1. Start the merge normally. Conflicts will cluster in `.gator/.includes/`.
2. Class A conflicts: `git checkout --theirs` (or `--ours`) each shipped path — whole files, no hand-merging.
3. Class B conflicts: real merges per §2.
4. Complete the merge commit.
5. Run `gator update` — it converges all shipped content to the installed CLI's canonical version and re-stamps `.gator-version`.
6. Commit the update's changes (see `procedures/committing-gator-files.md` — the answer is yes, commit them, `change-type: governance`).

### 3b. Branches on different Gator versions, no merge planned yet

**This is fine. Do nothing.** Each branch's `.gator/` content is self-consistent; `gator init` works per-branch. Do not proactively "fix" other branches — version convergence happens naturally at merge time via §3a. (A future Gator feature may update all branches in one operation; until then, per-branch convergence at merge time is the supported flow.)

### 3c. Origin is ahead (a teammate updated Gator and pushed)

`git pull`. Usually clean (adds and modifications, no conflicts). If conflicted, apply §2 rules. Afterward run `gator init` (refreshes hooks; shows the version banner) — and if your installed CLI is older than what the teammate used, `pipx upgrade gator-command` so future updates don't regress shipped content.

### 3d. Origin is behind (you updated Gator, teammates haven't pulled yet)

Push normally. Nothing else to do on your side — teammates' agents apply §3c on theirs.

### 3e. `.gator-version` conflicts specifically

Take either side; it's re-stamped by the next `gator update` regardless (the `cli-version` field stamps unconditionally on every successful update). Never hand-edit version numbers to "match".

## 4. What NOT to do

- Do NOT ask the operator to choose between Gator versions — the resolution is mechanical (latest installed CLI via `gator update`), and asking wastes their attention on routine flow.
- Do NOT abort or postpone a merge because of `.gator/` conflict volume — dozens of shipped-file conflicts resolve in one `--theirs` sweep + one `gator update`.
- Do NOT hand-merge shipped content, ever.
- Do NOT delete `.gator/` and re-gatorize to escape a messy merge — that destroys user-authored knowledge (Class B) along with the shipped content.
- Do NOT drop session snippets from either side.

## 5. Common failure modes without this procedure

- The agent asks the user "there are Gator file updates and merge conflicts — what should I do?" — the user has no idea, and shouldn't need one; this procedure IS the answer.
- Hand-merged shipped files produce Frankenstein `.includes/` content that matches no released version and confuses drift detection.
- Merges get aborted as "too conflicted" when 90% of the conflicts were one `gator update` away from resolving themselves.
- Charters merge textually but describe functions that no longer exist in the merged code.
- Snippet evidence files get deleted as "merge noise", breaking the transcripts-first evidence trail.

## 6. Related surfaces

- [`committing-gator-files.md`](committing-gator-files.md) — what to commit after the post-merge `gator update`.
- [`pre-gator-residue.md`](pre-gator-residue.md) — `.pre.gator*` backups, if the merge crosses a v1→v2 layout migration.
- [`charter-alignment.md`](charter-alignment.md) — verifying merged charters against merged code.
- The [constitution](../constitution.md) — the governance loop these merges land inside.
