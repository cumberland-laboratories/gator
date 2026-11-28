# Brainstorm: Mechanical Charter Freshness, Verification, and Leanness

**Date:** 2026-11-27
**Status:** Brainstorm (Architect + Agent). Exploratory ideas — not a design sketch or implementation plan.
**Source:** copied from the machine-local vault on 2026-11-27 so #114 and #115 can link to it; the two `vault/` links resolve only on the Architect's machine. Codex's review and the decided order are in #115.
**Goal:** Push as much charter verification, drift detection, and bloat prevention as possible into fast, deterministic, zero-token mechanical scripts — closing the gap between *"the charter was touched"* and *"the charter is present, true, and lean."*

---

## Context: What Gator Already Has Mechanically

Before inventing new machinery, it helps to anchor on the existing seams:

- **Shared `Covers` grammar (`charter_covers.py`, `gator-covers-v1`)** and **shared significance policy (`charter_significance.py`, `gator-significance-v1`, #105)** already unify `gator-charter-verify.py`, `gator-charter-lint.py`, `charter_report.py`, and the pre-commit hook (`precommit_charter.py`).
- **Git-private per-worktree cache convention** already exists under `$(git rev-parse --git-path <name>)` (`gator-charter-sync.json`, `gator-charters-report.json`, `gator-override/`).
- **`charter_report.py`** already computes a fast `input_fingerprint(repo_root)` over `HEAD`, `git ls-files -s`, porcelain status, charter `*.md` stats, and `.charterignore`.
- **Session-open constraint (Architect decision 2026-10-11):** `gator init` must never run blocking repo-wide scans on the foreground path (the old scan took ~20 s).

What is still missing mechanically falls into four buckets: **(1)** asynchronous repo-wide health wired into the commit loop, **(2)** concrete mechanical rules for keeping must-read files lean and knowing *when and how* to split them, **(3)** automated anti-bloat / anti-history checks, and **(4)** deeper mechanical truth checks (existence, drift debt, signatures, links, and tripwire anchors).

---

## Idea 1: Non-Blocking Background Check Triggered by `gator init` → Read at `pre-commit`

### The core loop
1. `gator init` checks a per-worktree Git-private cache:
   `$(git rev-parse --git-path gator-charter-health.json)`
2. If the cache is missing or its `head` / `input_fingerprint` is stale, `gator init` spawns a **detached background worker** (`gator charters check --background`, or a dedicated helper) and exits immediately — zero added latency to session opening.
3. The background worker runs the heavier mechanical checks once for the current `HEAD` (coverage gaps, `INDEX.md`↔`Covers` mismatches, stale symbols, stale tripwire refs, per-charter drift debt from recent non-Gator commits, and size/bloat budgets) and atomically writes `gator-charter-health.json`.
4. At `git commit`, `pre-commit` reads `gator-charter-health.json` in <5 ms (no repo-wide scan during commit!) and surfaces relevant findings.

### Design guardrails (so this doesn't become noisy or brittle)

- **Deduplication & process safety:**
  - Acquire a non-blocking lockfile (`gator-charter-health.lock` with PID + stale-age timeout, e.g., 5 minutes) so multiple `gator init` calls or worktree opens don't pile up workers.
  - Spawn fully detached (`start_new_session=True` on POSIX; `DETACHED_PROCESS | CREATE_NO_WINDOW` on Windows) with `stdin/stdout/stderr` bound to `DEVNULL` so vendor session hooks never inherit a pipe or hang waiting for EOF.
  - Atomic write via temp file + `os.replace()` with a versioned schema (`gator-charter-health-v1`).
- **Fail-open on missing or in-flight cache:**
  - If `pre-commit` runs before the background worker finishes, or the file is absent/malformed, `pre-commit` never waits and never blocks. It simply skips the background enrichment (or prints a quiet single-line note if desired).
- **Staleness handling:**
  - Record `head` and `generated_at` in the cache. If `HEAD` moved since the snapshot, treat repo-wide numbers as advisory/stale rather than authoritative.
  - Bonus: `post-commit` (or `gator init` on the next session) can optionally trigger a detached refresh when `HEAD` changes, keeping the cache warm for both `pre-commit` and the Dashboard!
- **Crucial ergonomics rule — Scope Filtering at `pre-commit`:**
  - **Never block Commit A because of pre-existing debt in unrelated Module Z.** That is how teams start using `--no-verify` or `warn` mode.
  - Instead, split what `pre-commit` does with the background cache into two layers:
    1. **Touched-charter spotlight (actionable):** Filter the cache to *only the charters covering the currently staged files*. If the charter you are touching right now has 3 ungoverned teammate commits of drift debt, a dead `File:` link, or is over its token budget, surface those right in the hook output and `whiteboard.md`.
    2. **Repo-wide one-liner (awareness):** At most one quiet footer line if repo-wide issues exist (e.g., `charter health (as of a1b2c3d): 96% covered · 2 charters drifted · 1 over budget — run 'gator charters report'`).
- **Bonus payoff for `gator init` itself:**
  - If `gator init` sees a *fresh* cache already on disk for current `HEAD`, it can display a 0-ms health line in the banner without violating the 2026-10-11 no-foreground-scan rule.

### Open questions for Idea 1
- Should any background finding *ever* escalate to a pre-commit block (even when filtered to touched charters), or should the background cache remain strictly advisory while staged-diff checks own all blocking rules? *(Leaning: strictly advisory from cache; blocking rules should always be 100% reproducible from the staged index alone so retries are deterministic.)*
- Should `gator-charter-health.json` merge with or replace `gator-charters-report.json` / `gator-charter-sync.json` so there is only one mechanical cache file per worktree?

---

## Idea 2: Keeping Must-Read Files Lean — Easy Mechanical Rules for Subdivision

From [2026-11-08-charter-size-and-context-research.md](../vault/artifacts/2026-11-08-charter-size-and-context-research.md), the cost that actually hurts models is **always-read context** (`constitution.md` + `INDEX.md` + `cross-cutting.md`, currently ~14K tokens) and **overgrown single-row charters** (where touching one small file forces reading 30–40 KB of unrelated module details).

### A. An easy, repeatable rule for splitting `cross-cutting.md`

Right now, `scripts-cross-cutting.md` mixes two very different kinds of content:
1. **Universal behavioral tripwires** (Python 3.9 floor, Windows reparse points, `import_sibling`, fail-closed JSON readers) — things *every* session genuinely needs before editing almost any file.
2. **Dense cross-module catalogs** (byte-identity test pin lists, JSON schema additive-field catalogs, commit-trailer consumer tables, package-data exception rules) — things only needed when touching specific boundaries.

**Simple rule — the "Two-Tier Cross-Cutting Rule":**
- **Tier 0 (`cross-cutting.md` — always read, strict budget ≤ 10–12 KB / ~3K tokens):**
  An item belongs in `cross-cutting.md` *only* if **all three** are true:
  1. It affects **3+ domain charters** (or the entire repo, like Python version floor / Windows path semantics).
  2. An agent can break it **silently** without touching the defining file.
  3. It can be stated in **≤ 5 lines**.
- **Tier 1 (Topic-scoped contract charters, routed via `INDEX.md` or `## Connections`):**
  Anything that is a *shared contract* across 2+ domains but is **scoped to a specific boundary** (e.g., `contracts-schemas-and-trailers.md`, `contracts-shipped-copies.md`, `contracts-packaging.md`) lives in its own slim charter and is:
  - Referenced by a **one-line pointer** in `cross-cutting.md` (`-> Shipped-copy byte-identity pins: see contracts-shipped-copies.md`), and/or
  - Listed on only the `INDEX.md` rows that actually touch those boundaries.

**Even simpler rule-of-thumb for any repo ("The 3-Domain / 5-Line Rule"):**
> *If a rule applies to fewer than 3 domains, move it to the owning domain charter and link it. If it applies to 3+ domains but takes more than 5 lines to explain, keep a 2-line tripwire in `cross-cutting.md` and move the reference table to a linked contract charter.*

### B. Easy mechanical rules for splitting *any* domain charter

Instead of relying on gut feel or a rigid line count, combine **three mechanical triggers**:

1. **Byte/Token Budget Trigger (replaces pure line count):**
   - `cross-cutting.md`: warn > 12 KB (~3K tokens), red > 18 KB
   - Domain charter: warn > 18 KB (~4.5K tokens), red > 25 KB
   - Any single `INDEX.md` row's total reading set (`cross-cutting` + all charters on that row): warn > 30 KB (~7.5K tokens)
   - *Why bytes/tokens instead of lines:* a 170-line charter with 2,000-byte mega-paragraphs costs more tokens than a crisp 260-line charter.
2. **Co-Change Clustering ("Git tells you where the seam is"):**
   - A tiny stdlib script (`gator charters split-hints <charter>`) reads `git log --name-only -n 200` for the files in a charter's `**Covers**` set and builds a co-change graph (which files change in the same commits) + static import graph.
   - **Subdivision rule:** If a charter exceeds its byte budget and its covered files split cleanly into 2+ components with low co-change / low cross-import edges (just like Loop split into State / Commands / Host, and Dashboard UI split into Shell / Views / Loop View), the script prints the exact suggested file groupings!
   - Even simpler fallback for repos with short git history: **split by subdirectory or architectural layer** (state/model vs. CLI/commands vs. UI/views vs. I/O/hosting) whenever a charter covers > 6–8 files and exceeds budget.
3. **The "Must-Read Session Tax" Meter (`gator charters budget`):**
   - Reports total tokens for:
     - Session opening (`GATOR_INIT.md` + `constitution.md` + `mission.md` + `roadmap.md`)
     - Always-read charter overhead (`INDEX.md` + `cross-cutting.md`)
     - Top 5 heaviest `INDEX.md` rows
   - Makes context bloat measurable on every release or dashboard refresh.

---

## Idea 3: Keeping History & Non-Essential Information Out of Charters

Models naturally drift toward writing *changelogs* and *test inventories* into charters because they just finished making a fix and want to record what they did. Prose rules in `charters/README.md` help, but **mechanical diff-scoped lint catches the habit at the exact moment it happens.**

### A. Concrete guidance (the "3-Cut Rule" for agents and humans)

Before adding or editing text in a charter, cut anything that fails these three tests:
1. **Present-tense contract test:** Does this describe what the system *requires today*, or *how it used to work / when it changed*?
   - *Bad:* "Before #16 it took the text before a heading's first `(`; on this repo that produced 19 false positives (2026-11-21)."
   - *Good:* "`_check_charter_function_refs()` parses compound headings via `charter_significance.heading_names()` and resolves `Covers` globs via `charter_covers`."
   - Where history goes: Git commit message (always) or `.gator/artifacts/` (only if durable decision rationale).
2. **One-grep test:** Can an agent discover this in one `grep` or by reading a 30-line function?
   - *Cut:* step-by-step algorithm narration, exhaustive helper inventories, raw lists of every test class name (`Pinned by tests/test_foo.py::TestBar` repeated 15 times).
   - *Keep:* ownership boundaries (`## Owns` / `## Does Not Own`), non-obvious invariants (`!`), cross-module callers/callees, file/state side effects, and *at most* one test anchor when a non-obvious contract has a single dedicated pin.
3. **Scannability test:** No wall-of-text paragraphs. One invariant or responsibility per short bullet (≤ 3–4 lines).

### B. Mechanical anti-bloat lint rules (zero LLM tokens)

Run in `gator-charter-lint.py` **and** as **diff-scoped advisory warnings on staged charter lines** in `pre-commit` (flagging only *newly added* lines so existing charters aren't noisy):

| Mechanical Rule | What it detects (regex / AST-free) | Why it works |
|---|---|---|
| `charter-history-narrative` | Past-tense / chronological phrases in added lines: `\bbefore #\d+\b`, `\bused to\b`, `\bformerly\b`, `\bwas removed\b`, `\bretired\b`, `\bsince v?\d+\.\d+`, `\bin 202\d\b`, `\b202\d-\d\d-\d\d\b` | Catches 80%+ of changelog creep the second an agent writes it. |
| `charter-issue-density` | High density of `#\d+` issue references or `v\d+\.\d+` version stamps (e.g., > 5 per 100 lines, or added issue refs outside a tripwire) | Issue numbers belong in commits, not live architecture maps. |
| `charter-dense-paragraph` | Any single non-table, non-`Covers` line > 500–600 characters (or unbroken prose block > 6 lines) | Forces crisp map notation; immediately flags mega-paragraphs like `scripts-cross-cutting.md` line 148. |
| `charter-test-inventory` | Lines citing multiple `test_*.py` / `Test*` / `test_*()` names, or > N test citations per charter | Stops charters turning into fragile mirrors of the test suite. |
| `charter-budget-exceeded` | Charter bytes > soft cap (e.g., 12 KB cross-cutting, 20 KB domain) | Prompts splitting before a charter reaches 40–70 KB. |
| `charter-code-dump` | Fenced code blocks > 10 lines inside a module charter (excluding `README.md`) | Charters map code; they don't copy code. |

---

## Idea 4: Other High-Leverage Mechanical Ideas (Existence, Truth, and Drift)

Here are the highest-leverage pure-mechanical checks that push Gator clearly beyond *"charter was touched"*:

### 4.1 Catch **brand-new uncharted files** at `pre-commit` (`uncharted-new-file`)
- **Gap today:** If a commit modifies an already-routed file *and* adds a brand-new code file in a new directory (matching zero `INDEX.md` rows and zero `Covers` entries), staging the first file's charter satisfies `charter-alongside-code` and `charter-index-gap`. The new file enters the repo completely uncharted!
- **Mechanical fix:** In `pre-commit`, check every newly added (`A`) staged non-exempt code file against `INDEX.md` + all charters' `**Covers**` lines (using `charter_covers.covers_match` + `_token_matches`). If a brand-new code file is claimed by *nothing*, warn (or block with Architect override) right at commit time: *"New code file `src/foo/bar.py` is not covered by any charter or `INDEX.md` row."*
- Directly answers *"verifying that charters are there"* for new code!

### 4.2 `INDEX.md` ↔ `Covers` Bidirectional Consistency (`index-covers-drift`)
- **Gap today:** `INDEX.md` (used by `pre-commit` and agents) and each charter's `**Covers**` line (used by `gator-charter-verify` and `charter_report`) are maintained separately and can silently disagree.
- **Mechanical fix:** Resolve every tracked source file through `INDEX.md` and through `charter_covers.coverage_index()`. Flag:
  - Files covered by a charter's `Covers` that `INDEX.md` doesn't route to that charter (agents won't find the charter!).
  - Files routed by `INDEX.md` to a charter whose `Covers` doesn't claim them (verifier thinks they're uncovered!).
  - Dead `Covers` entries or `INDEX.md` tokens that match zero tracked files.
- Pure stdlib, < 50 ms, zero false positives.

### 4.3 Mechanical **Silent Drift & Bypass Radar** (Git History Audit)
- **Gap today:** Non-Gator teammates and `--no-verify` commits can modify code without touching charters, leaving charters silently stale.
- **Mechanical fix** (runs in the `gator init` background worker and `gator charters report`):
  - For each charter, find its last modifying commit (`git log -n 1 --format=%H -- <charter>`).
  - Query commits touching any of that charter's `Covers` files *after* that commit (`<last_charter_sha>..HEAD`), inspecting `Gator-*` trailers:
    - Count **Architect-approved skips** (`Gator-Charter-Changed: override-skip`) — intentional, not silent drift.
    - Count **`warn`-policy commits** (`Gator-Commit-Policy: warn`) — visible soft debt.
    - Count **ungoverned / bypassed commits** (no `Gator-*` trailers at all) + total lines churned (`--numstat`).
  - Report per-charter **Drift Debt** (e.g., `4 ungoverned commits · +180/-42 lines since last charter update`).
  - Solves two major critiques from the Nov 13 market report at once: **non-user teammate drift** and **`--no-verify` bypass visibility**.

### 4.4 **Signature & Tripwire-Anchor Verification** (MEX-grade truth, stdlib-only)
- **Stale `TRIPWIRE` anchors (`stale-tripwire-ref`):** Extract backticked code identifiers / file paths from `## TRIPWIRE:` sections and `!` lines. If a referenced file path doesn't exist in `git ls-files`, or a referenced function/constant isn't found in the charter's covered files (or repo for cross-cutting), flag it! Tripwires are the highest-value lines in a charter; broken tripwire references silently rot trust.
- **Broken `## Connections` & `File:` links (`broken-charter-link`):** Verify every relative Markdown link in `## Connections` resolves to an existing file and every `File:` path exists in `git ls-files`.
- **Function signature drift (`signature-changed`):** For Python (via `ast`, already parsed!) and JS/TS (via regex), compare parameter names/arity written in a charter heading like `### build_report(repo_root)` against the real definition when that function is modified in a staged diff. If a documented public seam gained/lost required parameters, emit a targeted pre-commit warning: *"`build_report()` signature changed in code; verify its charter entry."*
- **Cross-module import edge drift (`boundary-edge-drift`):** `charter_significance.py` already extracts cross-charter imports! Check whether Charter A now imports from Charter B without mentioning Charter B in `## Connections`. That mechanically catches *architectural boundary creep* (the exact thing `## Does Not Own` and `## Connections` exist to protect).

### 4.5 **Auto-Targeted Charter Context on Demand** (`gator charters for <paths>` / tiny read-only `gator mcp`)
- Not a lint check, but directly reinforces freshness and leanness:
- A deterministic CLI command `gator charters for <file1> <file2>` (and optionally an MCP wrapper) prints **only**:
  1. The matching `INDEX.md` owning charters
  2. Matching `cross-cutting.md` tripwires (and any `## TRIPWIRE:` / `!` lines extracted from the owning charters)
  3. Any current drift debt from `gator-charter-health.json` for those exact files
- Helps both humans (before code review / PRs) and any AI tool (Claude, Codex, Gemini, Cursor, Antigravity) get just-in-time charter truth without loading 15K tokens upfront.

### 4.6 **Charter Decay / Freshness Watermark (Lightweight Optional PR Check)**
- Reuse the exact same mechanical engine (`gator charters report --json` + diff-scoped tripwire extraction) in a zero-dependency CI step or `gator charters pr-brief <base>..<head>`:
  - Lists every charter and `!` TRIPWIRE in the PR's blast radius
  - Flags uncovered new files, charter drift debt, and `--no-verify` / `warn` commits in the branch
  - Advisory by default — gives teams visibility without forcing every teammate to install Gator locally.

---

## Suggested Priority Order (Highest Signal-to-Effort First)

If turning these into concrete sketches / issues, here is a clean incremental sequence:

1. **Wave 1 — Quick mechanical wins (pure stdlib, low risk, immediate payoff):**
   - `uncharted-new-file` check at pre-commit (catches brand-new unrouted code files).
   - `index-covers-drift` + broken `File:` / `## Connections` link check + `stale-tripwire-ref` in `gator-charter-verify` / `lint`.
   - Diff-scoped anti-bloat lint warnings (`charter-history-narrative`, `charter-dense-paragraph`, `charter-budget-exceeded`) on staged charter edits.
2. **Wave 2 — Async background health loop (`gator init` → cache → `pre-commit` + Dashboard):**
   - Unify or build the detached background check writing `$(git rev-parse --git-path gator-charter-health.json)` with lockfile + `HEAD`/fingerprint binding.
   - Add Git-history **Silent Drift & Bypass Radar** (ungoverned commits + churn since last charter edit).
   - Wire scoped, non-blocking touched-charter spotlight + one-line repo summary into `pre-commit`.
3. **Wave 3 — Leanness & subdivision ergonomics:**
   - Adopt the **3-Domain / 5-Line Rule** to split `scripts-cross-cutting.md` (#94) as the dogfood proof.
   - Add `gator charters budget` (token cost per session open & per `INDEX.md` row) and `gator charters split-hints` (git co-change + import clustering).
4. **Wave 4 — Deeper truth & reach:**
   - Python/JS signature-drift & cross-charter `## Connections` edge-drift checks.
   - `gator charters for <paths>` / `pr-brief` / read-only `gator mcp`.

---

## Connections

- [Charter Tooling charter](../charters/scripts-charter-tooling.md) — `charter_covers.py`, `charter_significance.py`, `charter_report.py`, verifier and linter seams
- [Pre-Commit Governance charter](../charters/scripts-precommit.md) — `precommit_charter.py` and hook validation rules
- [Session Boot charter](../charters/scripts-repo-lifecycle.md) — `gator-init.py` nonblocking boot contract (2026-10-11 no-foreground-scan decision)
- [Charter size and context research](../vault/artifacts/2026-11-08-charter-size-and-context-research.md) — token budgets and why non-code-recoverable invariants matter
- [Gator market position](../vault/artifacts/2026-11-13-gator-market-position.md) — why "charter true vs. charter touched", non-user drift, and `--no-verify` bypass visibility are decisive
- [Charters health section sketch](2026-11-04-charters-health-section-sketch.md) — Tier 1 mechanical report and cache fingerprint design
