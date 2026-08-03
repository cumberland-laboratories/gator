# Charter: Installer and Boot

**Covers**: `src/gator_command/scripts/gatorize.py`, `src/gator_command/scripts/gatorize/helpers.py`, `src/gator_command/scripts/gatorize/vendor_hooks.py`, `src/gator_command/scripts/gatorize/entry_points.py`, `src/gator_command/scripts/gatorize/managed_block.py`, `src/gator_command/scripts/gatorize/post_install.py`, `src/gator_command/scripts/gatorize/morph.py`, `src/gator_command/scripts/legacy/memex-lint.sh`, `src/gator_command/scripts/legacy/memex-lint.py`, `.gator/scripts/gator-session-start.py`, `src/gator_command/templates/gator-starter/scripts/gator-session-start.py`, `src/gator_command/templates/gator-starter/scripts/gator-session-open.py`

## Owns

The initial installation and boot chain for Gator-governed repos:

- `gatorize.py` is the canonical cross-platform installer (Python). Handles all five install scenarios: fresh directory, clean git repo, existing .gator/ (upgrade), memex structure (morph), and dual presence (prompt). `ensure_repo_gitignore()` runs in the common tail (all scenarios including upgrade) to guarantee standard rules (vault, .vscode, __pycache__). Available via `gator gatorize <path>` from pipx install — template resolution and COMMAND_POST detection are package-install compatible. Auto-registers repos in `~/.gator/dashboard-repos.json` for standalone dashboard visibility. As of v2.4.0 (retire-gator-install plan, 2026-07-30), no scenario creates or switches to a `gator-install` branch — every scenario operates on the current branch in place.
- **Bash installer chain retired in v2.4.0** — `gatorize.sh`, `gatorize-lib.sh`, `gatorize-actions.sh`, `gatorize-post.sh` were shipped-but-unreachable artifacts (zero programmatic invocations; `cli.py:70` and the dashboard both routed to `gatorize.py`). All four files deleted per plan Stage 4. Git history preserves the original bash implementation for reference.
- `memex-lint.sh` (legacy, now at `scripts/legacy/`) owns read-only mechanical invariant checking for the Memex knowledge layer. No new development.

## Does Not Own

- Template content — that lives in `src/gator_command/templates/gator-starter/`.
- Overlay updates to existing repos — that is `gator-update.py` in the repo-lifecycle cluster.
- Per-repo boot display (for fleet repos) — that is `gator-init.py` in the repo-lifecycle cluster.
- Command-post `registry.md` — legacy PI-maintained command-post state; the installer does not read or write it (registration goes to `~/.gator/dashboard-repos.json`).
- Hook behavior post-install — the managed hook location is repo-local and platform-specific (`.git/gator-hooks` on Windows via `core.hooksPath`, `.git/hooks` elsewhere). Changes require re-running gatorize or a manual update.

---

### action_install_thin_link — DELETED
Removed in command-post retirement. No longer creates `.gator/command-post.md`.

<!-- Bash-installer function entries (### gatorize.sh, ### detect_scenario [gatorize-lib.sh],
     ### write_gator_version [gatorize-lib.sh], ### action_install_gator [gatorize-actions.sh],
     ### install_hooks [gatorize-actions.sh], ### action_upgrade_gator, ### action_morph_memex
     [gatorize-actions.sh], ### gator_init_block, ### action_install_product_source
     [gatorize-post.sh], ### action_install_entry_points [gatorize-post.sh],
     ### action_register [gatorize-post.sh]) removed in v2.4.0 with the bash chain.
     The equivalent Python functions are documented as ### entries below. -->

### git(*args, cwd=None)
File: `src/gator_command/scripts/gatorize/helpers.py`
Runs a git subprocess with the given arguments and optional working directory; returns `(stdout, success)`.
Filesystem: none directly (delegates to git CLI)
<- most action functions in gatorize.py

### log_step(msg)
File: `src/gator_command/scripts/gatorize/helpers.py`
Prints an indented step message to stdout for install progress display.
Filesystem: none
<- all action and install functions

### prompt(question, options="", default="", auto_yes=None)
File: `src/gator_command/scripts/gatorize/helpers.py`
Interactive user prompt; returns user input string or default on EOF/interrupt. `auto_yes` is an explicit opt-in for `--yes` mode: when `helpers.AUTO_YES` is True AND the caller passes `auto_yes=<value>`, returns `<value>` without reading stdin. Otherwise reads stdin normally. `auto_yes=None` (the default) is a no-op regardless of the flag — sites keep interactive behavior until they opt in.
Filesystem: none
<- `action_feature_branch()`, `action_install_entry_points()`, `main()` scenario 5

### confirm(question, default="Y", auto_yes=None)
File: `src/gator_command/scripts/gatorize/helpers.py`
Y/N confirmation prompt; returns boolean. `auto_yes` is an explicit opt-in for `--yes` mode: when `helpers.AUTO_YES` is True AND the caller passes `auto_yes=True/False`, returns that bool without reading stdin. `auto_yes=None` (default) preserves interactive behavior regardless of the flag.
Filesystem: none
<- `action_morph_memex()`, `main()`

### AUTO_YES / set_auto_yes(value) / get_auto_yes()
File: `src/gator_command/scripts/gatorize/helpers.py`
Module-level `AUTO_YES = False` sentinel, plus its setter and reader. `set_auto_yes(value)` is called exactly once — from `gatorize.py:main()` after argparse. `get_auto_yes()` returns the current bool. Sites do NOT gate on `AUTO_YES` themselves — they pass their opt-in through `helpers.prompt(auto_yes=)` / `helpers.confirm(auto_yes=)`, and those internal checks handle the short-circuit.
Filesystem: none
<- `gatorize.py:main()` (writer via `set_auto_yes`), `prompt()` / `confirm()` (readers of the module global)
! `AUTO_YES` is written exactly once, by `gatorize.py:main()` via `helpers.set_auto_yes()`. Do not mutate it from anywhere else — sibling submodules that need the flag should pass `auto_yes=<value>` at the call site, letting `prompt()` / `confirm()` do the gating. Direct submodule writes would fight the setter contract and defeat the plan/execute separation.
! Under the Individual/Enterprise product boundary: helpers.py is PACKAGE-ONLY (no template mirror). Q10 of the retire-gator-install plan (2026-07-30) retires the template `gatorize.py` in Stage 4; there is no template importer for `helpers.py` to keep in sync.

### main() [gatorize.py]
File: `src/gator_command/scripts/gatorize.py`
CLI entry point. `argparse`: positional `target` (directory to gatorize), `--yes` / `-y` flag (non-interactive mode). After argparse, calls `helpers.set_auto_yes(args.yes)` — the single write path for the module-level sentinel. Resolves target path, self-gatorize guard, template check, scenario detection. Then: prints `print_pre_action_summary()` (scenario-aware), runs `_check_dirty_tree_and_gate()` for scenarios 2-5, prompts a Y/n confirmation (`confirm(..., auto_yes=True)` — under `--yes` auto-proceeds; interactive: `n` exits cleanly). Only after those gates does the scenario dispatch fire. No scenario creates or switches to `gator-install` — every scenario operates on the current branch in place. Scenario 5 (dual memex + gator) explicitly refuses under `--yes` with exit code 1, because the m/u choice has permanent data-shape consequences.
Filesystem: target directory (R for detection, W via delegated actions)
<- `gator gatorize` CLI, dashboard `resolve_repo_gatorize()`, test harnesses
! The `helpers.set_auto_yes(args.yes)` call is the ONE authoritative writer of `helpers.AUTO_YES`. Anywhere else touching the sentinel is a governance violation of the Stage 2 opt-in contract.
! `print_summary()` is called with the current branch captured POST-dispatch via `git rev-parse --abbrev-ref HEAD` (Stage 5 rewrite, 2026-07-30). Do NOT capture pre-dispatch — Scenario 1 has no `.git/` before `action_git_init()` runs. Fall back to `"(current branch)"` on rev-parse failure so the summary still prints.
! Scenario 5 under `--yes` exits 1 with a message stating that morph vs upgrade is a strategic decision requiring an interactive session. Do not weaken this to a default choice.
! Per-site `--yes` opt-ins for `helpers.confirm()` / `helpers.prompt()` currently exist at three sites: `entry_points.py:215` (`auto_yes="1"`, foreign entry-point Backup & replace), `gatorize.py` Scenario 5 (`auto_yes="x"`, refuse), and `gatorize/morph.py:52` (`auto_yes=True`, proceed with morph — Codex Stage-3 finding remediation, 2026-07-30). Adding any new interactive prompt in the installer flow requires deciding its `--yes` behavior at the same time; otherwise Dashboard-triggered gatorize will hang until subprocess timeout on Scenarios that reach the new prompt.

### copy_tree_overlay(src, dest)
File: `src/gator_command/scripts/gatorize/helpers.py`
Recursively copies files from src to dest, preserving extras in dest; skips `__pycache__` and `.pyc`.
Filesystem: src (R), dest (W)
<- `action_install_gator()`, `action_morph_memex()`

### detect_scenario(target)
File: `src/gator_command/scripts/gatorize.py`
Returns scenario number 1-5 based on presence of `.git/`, `.gator/`, and `memex/`/`.memex/` in target.
Filesystem: target directory (R)
<- `main()`

### detect_generation(target)
File: `src/gator_command/scripts/gatorize.py`
Returns generation number of an existing `.gator/` install: 0 (no markers), 1 (has `command-post.md` but no `.gator-version`), 2+ (reads from `.gator-version`).
Filesystem: `.gator/.gator-version` (R), `.gator/command-post.md` (R)
<- `main()` scenario 3 and 5

### _git_default_branch()
File: `src/gator_command/scripts/gatorize.py`
Reads `git config --get init.defaultBranch`. Returns the configured name or `"main"` if unset. Used by `action_git_init()` to name the initial branch on Scenario 1.
Filesystem: none (git config read)
<- `action_git_init()`

### action_git_init(target)
File: `src/gator_command/scripts/gatorize.py`
Scenario 1: initializes git in a fresh directory, creates an initial commit, and leaves the caller on git's default branch (from `_git_default_branch()`). Does NOT create a `gator-install` safety branch — that pattern was retired in v2.4.0 (see plan `2026-07-30-retire-gator-install-branch-implementation-plan.md`, Stage 3).
Filesystem: target `.git/` (W)
<- `main()` scenario 1
! No branch switch after `git init`. If future scenarios need a per-user default branch, thread it in via the `_git_default_branch()` helper — do not hardcode.

### print_pre_action_summary(target, scenario)
File: `src/gator_command/scripts/gatorize.py`
Prints a scenario-aware preview of what gatorize is about to do, before any filesystem mutation. Scenario 1 says "Gatorizing new directory at <target>" — no branch name, no safety-branch hint (nothing to branch from). Scenarios 2-5 read the current branch via `git rev-parse --abbrev-ref HEAD` and say "Gatorizing branch '<name>' at <target>", plus a safety-branch hint ("Want a safety branch? Cancel and run: git checkout -b my-gator-experiment"). Uses the `SCENARIO_DESCRIPTIONS` module-level dict for the scenario label.
Filesystem: none directly (git rev-parse for the branch name)
<- `main()` (all scenarios, immediately after scenario detection)
! Scenario 1 must NOT print the "Gatorizing branch" phrase — a Codex Round-6 regression guard test pins this.

### _check_dirty_tree_and_gate(target)
File: `src/gator_command/scripts/gatorize.py`
Checks `git status --porcelain`. On dirty tree: under `--yes` (helpers.get_auto_yes() True), prints an error and `sys.exit(1)`; interactive, prompts continue/abort — abort exits 0 cleanly. Clean tree: returns silently. Only called by `main()` for scenarios 2-5 (Scenario 1 has no git repo yet).
Filesystem: none directly (git status read)
<- `main()`

### action_install_gator(target)
File: `src/gator_command/scripts/gatorize.py`
Fresh install with v2 layout: creates `.gator/` user-visible directory tree and `.gator/.includes/` for shipped content. Shipped root files (constitution, startup guide, charterignore) go to `.includes/`. Shipped directories (scripts, reference-notes) go to `.includes/`. Mixed directories (procedures, charters, blueprints) are split: scaffolding (`_template.md`, `README.md`) goes to the user-visible root, shipped content (procedures, reference-notes) goes to `.includes/`. User-content directories (docs, artifacts, threads, etc.) go to root. Writes `layout-version.json`. Installs slash commands, hooks, stubs, and `.gator-version`.
Filesystem: target `.gator/` (W), `.gator/.includes/` (W), `$TEMPLATES/` (R), `target/.claude/commands/` (W)
<- `main()` scenarios 1 and 2, `action_morph_memex()` when no existing `.gator/`
! Scaffolding files (`_template.md`, `README.md`) must go to root, not `.includes/` — agents look for them when creating new content.

### install_hooks(target)
File: `src/gator_command/scripts/gatorize.py`
Installs three hooks (`pre-commit`, `commit-msg`, `post-commit`) via `gator-update.install_git_hooks()`; backs up existing non-Gator hooks with `.pre-gator` suffix.
Filesystem: managed hook dir (W), `.git/config` (W on Windows), `*.pre-gator` backups (W)
<- `action_install_gator()`

### write_stubs(gator_dir)
File: `src/gator_command/scripts/gatorize.py`
Writes stub content files (mission, roadmap, inbox, identity, issues, commit_draft, patterns, whiteboard, config, lint-allow, commit_issues, charter INDEX, sessions .gitignore, vault .gitkeep) only if missing.
Filesystem: `gator_dir/*.md`, `gator_dir/*.json`, `gator_dir/charters/INDEX.md`, `gator_dir/sessions/.gitignore`, `gator_dir/vault/.gitkeep` (W, create-only)
<- `action_install_gator()`

### ensure_repo_gitignore(repo_root)
File: `src/gator_command/scripts/gatorize.py`
Ensures `.gitignore` contains standard rules for vault, `.vscode/`, `__pycache__/`, `.gator/active-vendor-session.json` (machine-local vendor session identity), `.gator/session-blocks/` (local-only transcript evidence), hook ephemera (`.gator/whiteboard.md`, `.gator/commit_draft.md`, `.gator/status.json` — written and cleared each commit cycle, cause merge conflicts if tracked), and local agent companion files (`AGENTS.local.md`, `CLAUDE.local.md`, `GEMINI.local.md` — personal per-machine agent notes/skills; installer-untouched, never read or written by Gator, only gitignored). Appends missing rules. Also called by `gator-update.py` for gitignore convergence on existing repos.
! Local companion rules are the *only* place any Gator code path mentions `*.local.md` filenames. No installer, updater, or state-inspection code reads, writes, creates, or deletes those files. That is the ownership boundary (Stage 1 of the local-overrides + managed-state plan, artifact `2026-07-28-local-agent-overrides-and-managed-state-plan.md`).
Filesystem: `repo_root/.gitignore` (RW)
<- `write_stubs()`, `main()` common tail, `gator-update.main()` via `import_sibling("gatorize")`

### write_gator_version(gator_dir, action)
File: `src/gator_command/scripts/gatorize.py`
Writes `.gator-version` with generation, install date, update timestamp, action type, installer name, and cli-version (resolved via `gator_core.get_version()`); preserves original install date on upgrade.
Filesystem: `.gator/.gator-version` (RW)
<- `action_install_gator()`, `action_morph_memex()`

### GATOR_BEGIN, GATOR_END, BlockState, ManagedBlockLocation
File: `src/gator_command/scripts/gatorize/managed_block.py`
Sentinel byte constants (`<!-- GATOR:BEGIN -->`, `<!-- GATOR:END -->`), the canonical six-state `BlockState` enum (`CLEAN | MODIFIED | LEGACY | CORRUPTED | ABSENT | FOREIGN`) whose `.value` strings are the wire format for all JSON output and human text, and the `ManagedBlockLocation` dataclass returned by `find_managed_block()` (`before`, `block_content`, `after` slices plus `begin_index` and `end_index` byte offsets). Re-exported from `entry_points.py` so existing importers (`gatorize.py:49-51`) keep working after the Stage 3 extraction.
<- `entry_points.py`, `gatorize.py` (via `entry_points` re-export), future `gator-state.py` (Stage 4), future `gator-update.py` block-refresh (Stage 4b)
! Sentinel bytes are the ownership contract with every gatorized repo. Do NOT mutate — whitespace, casing, or attributes. See Invariant #1 of `2026-07-28-local-agent-overrides-and-managed-state-plan.md`.
! `BlockState.value` strings (`"clean"`, `"modified"`, …) are the canonical vocabulary. All API constants, JSON schema values, human output, and test fixtures MUST use these exact lowercase spellings.

### find_managed_block(text)
File: `src/gator_command/scripts/gatorize/managed_block.py`
Returns a `ManagedBlockLocation` when the text contains exactly one well-formed sentinel pair (BEGIN before END), else `None`. Callers that need to distinguish "corrupted sentinels" from "no sentinels at all" must use `classify_managed_block()` instead — `find_managed_block()` collapses both to `None` by design.
Filesystem: none (pure string operation)
<- `classify_managed_block()`, future `gator state repair` (Stage 4)
! Returns `None` for malformed sentinels (dangling BEGIN, dangling END, reversed order, duplicated BEGIN, duplicated END). The `action_install_entry_points()` case-1 refresh path does NOT use this — it keeps its historical "first BEGIN + first END" tolerance to avoid behavior change during the Stage 3 refactor.

### render_managed_region(baseline_content)
File: `src/gator_command/scripts/gatorize/managed_block.py`
Returns the exact bytes that should appear between `GATOR_BEGIN` and `GATOR_END`, given a baseline content string (typically `render_entry_content()` output). Centralizes the newline wrapping so installer, `gator state repair` (Stage 4), and `gator update` block-refresh (Stage 4b) all produce byte-identical managed regions.
Filesystem: none (pure string operation)
<- `upgrade_legacy_entry_point()`, `action_install_entry_points()`, `classify_managed_block()`, future `gator-state.py`, future `gator-update.py` block-refresh
! The current contract is `f"\n{baseline_content}\n"`. Changing this contract requires updating every caller in lockstep or existing `clean` files will report `modified` on the next `gator state status`.

### detect_legacy_gator_content(text)
File: `src/gator_command/scripts/gatorize/managed_block.py`
Returns `True` when the file has no sentinel pair but matches recognizable Gator content — checks the four fingerprint strings `GATOR_MARKER`, `COMMAND_POST_MARKER`, `"gator-init.py"`, `".gator/constitution.md"`. Sentinels alone do not count as legacy.
Filesystem: none (pure string operation)
<- `classify_managed_block()`, `action_install_entry_points()` (case-2 dispatch), future `gator state repair` (Stage 4), future `gator update` block-refresh (Stage 4b)

### classify_managed_block(text, baseline_content, *, file_exists)
File: `src/gator_command/scripts/gatorize/managed_block.py`
Returns a `BlockState` for an entry-point file. Dispatch order: `file_exists=False` → `ABSENT`; valid sentinel pair → `CLEAN` or `MODIFIED` by byte-compare against `render_managed_region(baseline_content)`; malformed sentinels → `CORRUPTED`; no sentinels + legacy fingerprint → `LEGACY`; no sentinels + no fingerprint → `FOREIGN`. `baseline_content` is the raw content (typically `render_entry_content()` output) — the function wraps it internally via `render_managed_region()` so callers do not need to know the newline contract.
Filesystem: none (pure classification)
<- future `gator-state.py` (`main_status()`, `main_repair()`) (Stage 4), future `gator-update.py` block-refresh (Stage 4b)
! Baseline is host-scoped — see Invariant #8 of `2026-07-28-local-agent-overrides-and-managed-state-plan.md`. `CLEAN` means "matches the currently-resolved template on this host," not version-pinned; a host `gator` upgrade may flip files from `CLEAN` to `MODIFIED` even with no local edits.

### render_entry_content(has_command_post, agent_type="claude")
File: `src/gator_command/scripts/gatorize/entry_points.py`
Renders the canonical Gator-managed instruction block for an entry-point file, with optional command-post section and agent-specific additions. This is the **single source of truth** for cross-vendor agent orientation — all model-facing instructions (gator init, gator pulse, gator loop join, project assessment, local-companion precedence) are defined here once and deployed to CLAUDE.md, AGENTS.md, and GEMINI.md identically (except agent-specific additions like the Codex enforcer note). Includes a `local_companion_block` — a two-paragraph "Personal skills / Team-shared skills" section — with `<VENDOR>` interpolated from `agent_type.upper()` so each file references its own `CLAUDE.local.md` / `AGENTS.local.md` / `GEMINI.local.md`. The block also carries the precedence contract: local guidance may extend behavior but MUST NOT override Gator governance or repo-shared instructions. This precedence wording is a load-bearing contract, not just documentation — see `2026-07-28-local-agent-overrides-and-managed-state-plan.md` Invariant #9.
Filesystem: none (returns string)
<- `action_install_entry_points()`
! Adding a new agent-facing instruction (like "gator loop join") means adding it here — it automatically propagates to all three vendor entry points on next gatorize/update. Claude Code also gets a slash command via `templates/gator-starter/commands/`, but Codex and Gemini rely solely on this text block.
! The corresponding `.claude/commands/*.md` files are a convenience layer for Claude Code's slash-command UX. They are NOT the source of truth — this function is. If the instruction text diverges between here and the command file, reconcile to this function.
! The `local_companion_block` wording must appear verbatim across all three vendors — the precedence contract ("local may extend, MUST NOT override") is the agent-facing enforcement mechanism for the ownership model. Detailed examples and the team-vs-personal decision guide live in the shipped reference-note at `templates/gator-starter/reference-notes/local-agent-skills.md`, distributed via the standard `reference-notes/` overlay (v1: `.gator/reference-notes/`, v2: `.gator/.includes/reference-notes/`).

### action_install_entry_points(target, has_command_post)
File: `src/gator_command/scripts/gatorize/entry_points.py`
Installs or refreshes `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` using `<!-- GATOR:BEGIN/END -->` sentinels; four cases: missing (create), Gator-managed (refresh block in place), legacy Gator (`detect_legacy_gator_content()` matches — delegated to `upgrade_legacy_entry_point()`), non-Gator (interactive prompt with backup/append/overwrite/cancel). Since Stage 3, sentinel constants and the legacy fingerprint check come from `gatorize.managed_block`; case-1 refresh still uses inline first-BEGIN/first-END string splicing (byte-preserved from pre-Stage-3 behavior — do not route through `find_managed_block()` without a plan-level review, that would change duplicated-sentinel tolerance). Under `--yes`, the non-Gator prompt auto-picks `"1"` (Backup & replace) via `auto_yes="1"` at the call site.
Filesystem: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` at target root (RW), `*_ROLLBACK.md` backups (W)
<- `main()` common tail
-> `render_entry_content()`, `upgrade_legacy_entry_point()`, `render_managed_region()`, `detect_legacy_gator_content()`
! Cancellation `[x]` branch prints an HONEST partial-cleanup hint (Stage 5, 2026-07-30): it names the entry-point files that may already be on disk and gives platform-appropriate remove recipes, plus the safety-branch discard recipe. The recipes are `sys.platform`-aware — Windows prints a PowerShell `Remove-Item -Force` recipe (with the `rm -f` bash form as a "or from Git Bash / WSL" alternative), non-Windows prints the plain `rm -f` recipe (Codex Stage-5 finding remediation). Do NOT reintroduce the pre-Stage-3 hint (`git checkout dev && git branch -D gator-install`) — gatorize is single-branch as of Stage 3, so no branch-delete undoes anything. Do NOT collapse the platform branch back to a single `rm -f` recipe — Windows CMD does not have `rm` and PowerShell's `rm` alias uses different flag semantics.

### upgrade_legacy_entry_point(target, filename, has_command_post, agent_type)
File: `src/gator_command/scripts/gatorize/entry_points.py`
Upgrades a legacy Gator entry-point file (fingerprints present but no sentinel pair) in place, rewriting with a fresh sentinel-wrapped managed block while preserving any `## Pre-Gator Instructions` section. Behavior-preserving refactor of the pre-Stage-3 case-2 logic inline in `action_install_entry_points()`. Header/filename resolution goes through the module-local `_ENTRY_POINT_META` mapping.
Filesystem: `target/filename` (RW)
<- `action_install_entry_points()` case-2 dispatch, future `gator state repair` (Stage 4) when it encounters `BlockState.LEGACY`
-> `render_entry_content()`, `render_managed_region()`
! Byte-format contract: `f"{pre_gator}\n\n{managed_block}{post_gator}\n"` when a marker was found, else `f"{header}\n\nYou are the primary agent for this project.\n\n{managed_block}{post_gator}\n"`. Snapshot tests in `tests/test_gatorize.py` (Stage 3) pin this against the pre-refactor output for representative fixtures.

### action_install_outbox(target)
File: `src/gator_command/scripts/gatorize/post_install.py`
Creates `outbox.md` stub at target root; preserves existing file if it has content.
Filesystem: `target/outbox.md` (W, create-only if content exists)
<- `main()` common tail

### action_install_product_source(target, scripts_dir, today)
File: `src/gator_command/scripts/gatorize/post_install.py`
Writes `.gator/product-source.json` with package root path and template directory layout. Always uses package root (command-post source path retired).
Filesystem: `.gator/product-source.json` (W)
<- `main()` common tail

### action_register(target, today)
File: `src/gator_command/scripts/gatorize/post_install.py`
Registers repo in `~/.gator/dashboard-repos.json` via `gator_core.add_dashboard_repo()`. Command-post `registry.md` registration removed.
Filesystem: `~/.gator/dashboard-repos.json` (W)
<- `main()` common tail

### print_summary(target, scenario, current_branch)
File: `src/gator_command/scripts/gatorize/post_install.py`
Renders the SUCCESS banner with finalization git instructions (`git add -A && git commit ...` on the current branch), a scenario-aware "Not what you wanted?" recovery paragraph, and enforcement level. As of v2.4.0 (retire-gator-install plan Stage 5, 2026-07-30) the parameter is `current_branch` (was `gator_branch`) — the caller reads it POST-dispatch via `git rev-parse --abbrev-ref HEAD` because Scenario 1 has no `.git/` pre-dispatch. Callers use the placeholder `"(current branch)"` if the read fails; the summary must not crash on the last mile.
Filesystem: none (stdout only)
<- `main()` common tail
! Recovery paragraph is scenario-aware and points at the safety-branch pattern (`git checkout -b my-gator-experiment` BEFORE running gatorize) as the load-bearing supported clean-undo path. Do NOT reintroduce naive `git checkout .` or blanket `git reset --hard` recipes — `git checkout .` does not remove untracked new files (which is most of what gatorize installs on a fresh scenario), and `git reset --hard` becomes destructive once Stage 3's interactive dirty-tree continuation is a supported path. Codex Round-3 Finding 2 remediation.
! Argument is captured POST-dispatch, not pre-dispatch. Scenario 1's `action_git_init()` creates the initial branch during dispatch — the branch does not exist beforehand. Codex Round-6 Finding 2 remediation.

### detect_legacy_memex(target)
File: `src/gator_command/scripts/gatorize/morph.py`
Returns a dict indicating which legacy memex structures exist: `memex/`, `.memex/`, root `constitution.md`, root `constitution-core.md`.
Filesystem: target directory (R)
<- `action_morph_memex()`, `main()` scenario 5

### action_morph_memex(target, action_install_gator, write_gator_version, scripts_dir)
File: `src/gator_command/scripts/gatorize/morph.py`
Scenario 4: renames legacy memex dirs to `*.pre-gator/` (via `git mv` or `shutil.move`), installs or upgrades `.gator/`, migrates content into `.gator/`, archives root constitution files to `.gator/legacy-constitution*.md`.
Filesystem: `memex/` or `.memex/` (renamed), `.gator/` (W), root `constitution.md` (moved)
<- `main()` scenarios 4 and 5

---


### memex-lint.sh [legacy]
File: `src/gator_command/scripts/legacy/memex-lint.sh`
Read-only mechanical invariant checker for the Memex knowledge layer. Validates: budget file sizes (identity.md, active threads, patterns, inbox.md included in line count), link integrity, orphan detection.
Filesystem: `gator-command/` (R only — never writes)
<- manual invocation; CI/CD if configured
! Exit code equals the error count (`exit $ERRORS`) — warnings do not affect the exit code, but multiple errors produce exit codes greater than 1. Do not assume exit 1 means exactly one error. Thresholds (budget sizes, counts) are hardcoded in the script — update both the script and companion procedure docs together if they change.

---

## TRIPWIRE: Five-Scenario Invariants

Scenario detection is exhaustive — exactly one scenario is returned for any valid input:

| Scenario | has_git | has_memex | has_gator | Action |
|---|---|---|---|---|
| 1 | ✗ | ✗ | ✗ | git init + full install |
| 2 | ✓ | ✗ | ✗ | full install |
| 3 | ✓ | ✗ | ✓ | upgrade (overlay only) |
| 4 | ✓ | ✓ | ✗ | morph (migrate + install) |
| 5 | ✓ | ✓ | ✓ | warn + exit (manual PI operation) |

Scenario 1 creates the git repo before installing. Scenario 4 renames the legacy memex dir to `memex.pre-gator/` and preserves it for PI review — it is not deleted. **No scenario creates or switches to a `gator-install` branch** — that pattern was retired in v2.4.0 (see plan `2026-07-30-retire-gator-install-branch-implementation-plan.md`, Stage 3). Every scenario now operates on the current branch in place. Rollback is via the standard safety-branch pattern: cancel the interactive Y/n gate, run `git checkout -b my-gator-experiment`, re-run `gatorize`.

## TRIPWIRE: GATOR_GEN Read from gator_core.py

`CURRENT_GENERATION` in `gator_core.py` is the single source of truth for the current install generation. The Python installer imports it directly (`from gator_core import CURRENT_GENERATION`). If `gator_core.py` is unavailable on a deployed install, downstream code falls back to `2`. Keep `CURRENT_GENERATION = N` on exactly one line with no variation.

## TRIPWIRE: gatorize.py Package/Template Copy Sync — RETIRED

Retired in v2.4.0 (retire-gator-install plan Stage 4, 2026-07-30). `gatorize.py` now exists only in `src/gator_command/scripts/gatorize.py`. The template copy at `src/gator_command/templates/gator-starter/scripts/gatorize.py` was deleted because:

1. It imported from a `gatorize/` sub-package that isn't shipped to the template tree — every fleet-repo load failed at import time and was silently swallowed by the `try/except ImportError` in fleet-repo `gator-update.py:41`.
2. No code path ever successfully loaded the template copy — it was a shipped-but-unreachable artifact, same class as the bash chain.

Fleet-repo behavior after retirement: `import_sibling("gatorize")` in fleet-repo `gator-update.py:41` continues to return None; the outer `try/except` still yields `ensure_repo_gitignore = lambda repo_root: None`. Silent-degradation outcome identical to today, but with no phantom broken file on disk. Invariant #14 in the local-agent-overrides plan (2026-07-28) is retired with this tripwire.

The pre-commit hook trio sync obligation and the `gator-update.py` copy sync obligation are unchanged. Only `gatorize.py`'s template copy is retired.

---

### detect_vendor(payload)
File: `.gator/scripts/gator-session-start.py`
Detects vendor from hook payload fields. Checks explicit `vendor` field (with alias normalization: `claude`→`anthropic`, `codex`→`openai`, `gemini`→`google`), then model name hints, then `GEMINI_SESSION_ID` env var as last resort. Returns canonical vendor name (`anthropic`, `openai`, `google`, `unknown`). Uses `_get_str()` for nested payload support.
<- `build_session_file()`

### extract_vendor_session_id(payload)
File: `.gator/scripts/gator-session-start.py`
Extracts vendor session ID from hook payload. Payload always wins over env vars (prevents stale env contamination). Tries `session_id`, `sessionId`, `id` at top level and one level of nesting. Falls back to `GEMINI_SESSION_ID`/`CLAUDE_SESSION_ID` env vars only when payload has nothing.
<- `build_session_file()`

### build_session_file(payload)
File: `.gator/scripts/gator-session-start.py`
Builds `active-vendor-session.json` content from vendor hook stdin payload. Returns dict or None if no usable session ID. Extracts vendor, session_id, model, transcript_path, cwd, and started_at.
<- `main()`
-> `detect_vendor()`, `extract_vendor_session_id()`, `extract_model()`, `extract_transcript_path()`, `extract_cwd()`, `extract_started_at()`

### write_session_file(gator_dir, data)
File: `.gator/scripts/gator-session-start.py`
Atomic write of `.gator/active-vendor-session.json` via temp-file-and-rename. Machine-local, gitignored.
@writes: `.gator/active-vendor-session.json`
<- `main()`
! Temp file cleanup is explicit on failure. Never leaves partial writes.

### main()
File: `.gator/scripts/gator-session-start.py`
Entry point for vendor `SessionStart` hooks. Reads stdin JSON, builds session file, writes atomically. Always exits 0 — never blocks the vendor session. Cross-vendor: handles Claude Code, Codex CLI, Gemini CLI payloads.
@reads: stdin (JSON from vendor hook)
@writes: `.gator/active-vendor-session.json`
! This script is distributed as a template (`gator-starter/scripts/`) so fleet repos receive it on `gator update`.

---

### find_gator_dir()
File: `src/gator_command/templates/gator-starter/scripts/gator-session-open.py`
Walks up from cwd to find a repo-level `.gator/` directory. Requires a sibling `.git/` to distinguish governed repos from the machine-local `~/.gator` config directory. Returns the `.gator/` Path or None.
Filesystem: cwd ancestry (R)
<- `main()`
! The `.git/` sibling check is essential — without it, any vendor session launched under the home tree matches `~/.gator`, leading to spurious bootstrap attempts and stderr noise.

### main()
File: `src/gator_command/templates/gator-starter/scripts/gator-session-open.py`
Entry point for silent self-heal at vendor session start. Finds repo-level `.gator/`, resolves the scripts directory via a v2-first probe (`.gator/.includes/scripts/` → `.gator/scripts/` fallback), bootstraps sys.path from the resolved candidate, calls `get_gator_paths(repo_root)` from `gator_layout`, and passes the resulting `GatorPaths` (not a raw `Path`) into `ensure_git_hooks()`. Bails silently on `layout == "invalid"`. Captures `ensure_git_hooks()`'s return dict into a local for future observability wire-up (currently discarded — B3 will route non-happy-path statuses into a bounded diagnostic log). Always exits 0 — never blocks the vendor session. Never writes to stdout. Errors go to stderr with `gator-session-open:` prefix via the `__main__` guard's try/except.
@reads: `.gator/.includes/scripts/gator-init.py` (v2, primary) or `.gator/scripts/gator-init.py` (v1 fallback)
@writes: `.git/hooks/` (only when hooks are missing or stale)
! This script runs before `gator-session-start.py` in the vendor hook list. Both are independent — no ordering guarantee is assumed. The split ensures correctness (hook self-heal) without requiring the user to type `gator init`.
! Distributed as a template (`gator-starter/scripts/`) so fleet repos receive it on `gator update`.
! Prior v1-only implementation hardcoded `scripts_dir = str(gator_dir / "scripts")` and passed the raw `gator_dir` into `ensure_git_hooks()` which expects a `GatorPaths`. On v2 repos this raised `AttributeError` and the `__main__` guard's `except → sys.exit(0)` swallowed it, making the "silent self-heal" a silent no-op fleet-wide. The v2-first probe + `get_gator_paths()` is the fix; keep the `GatorPaths` contract with `ensure_git_hooks()` (see `gator-init.py::ensure_git_hooks()` for the reader side).

### merge_hooks_into_settings(settings_path, hooks_template_path)
File: `src/gator_command/scripts/gator-update.py`, `src/gator_command/scripts/gatorize.py`, `src/gator_command/templates/gator-starter/scripts/gator-update.py`
Merge-safe injection of Gator hooks into vendor settings JSON. Creates file if missing, deep-merges hooks block if present. Finds the existing Gator group (identified by `.gator/` in command strings), separates Gator hooks from user hooks in the group, and rebuilds it with template Gator hooks followed by preserved user hooks when the Gator commands or ordering differ. Falls back to appending a new group if no Gator group exists. Never clobbers existing permissions, env vars, or user hooks — including user hooks mixed into the same group as Gator hooks.
@writes: vendor settings file (e.g., `.claude/settings.json`)
<- `install_vendor_hooks()`
! Corrupt or non-dict JSON is never overwritten — returns 'unchanged' and leaves the file intact.
! Validates shape defensively: hooks must be dict, each event value must be list. Malformed shapes (hooks as list, event as string/dict) are skipped without crashing — the installer must never fail on a user-edited vendor config.

### _extract_hook_commands(groups)
File: `src/gator_command/scripts/gator-update.py`, `src/gator_command/scripts/gatorize.py`, `src/gator_command/templates/gator-starter/scripts/gator-update.py`
Extracts all `command` strings from a list of vendor hook groups. Used by `merge_hooks_into_settings()` to compare existing vs template hook commands for incremental merge.
<- `merge_hooks_into_settings()`

### install_vendor_hooks(templates_dir, repo_root)
File: `src/gator_command/scripts/gator-update.py`, `src/gator_command/scripts/gatorize.py`, `src/gator_command/templates/gator-starter/scripts/gator-update.py`
Installs vendor `SessionStart` hook configs for Claude Code, Codex CLI, and Gemini CLI. Reads templates from `vendor-hooks/` directory, writes to `.claude/settings.json`, `.codex/hooks.json`, `.gemini/settings.json` via `merge_hooks_into_settings()`. Returns count of files changed.
<- `main()` (gator-update.py, including template-deployed copy), `action_install_gator()` (gatorize.py)
-> `merge_hooks_into_settings()`
! The `vendor-hooks/*.json` templates MUST reference script paths at `.gator/.includes/scripts/` (v2 layout). Reverting to `.gator/scripts/` (v1) silently breaks every v2 fleet repo because `merge_hooks_into_settings` compares template commands to existing commands and only rewrites on mismatch — a v1-path template plus a v1-path existing settings file looks like "no change needed" even though the target script doesn't exist under v2. The v1→v2 template drift is the root cause of the 2026-08-03 begin-session fleet-wide silent no-op fix set (see plan `.gator/vault/artifacts/2026-08-03-update-and-begin-session-bugs-implementation-plan.md`).

---

## Before Changing This Module

- Adding a new install scenario requires updating: `detect_scenario()` in `gatorize.py`, the scenario dispatch in `gatorize.main()`, the scenario invariant table above, and `.gator/procedures/gatorize-permutations.md`.
- The idempotency marker strings in `gatorize/helpers.py` (GATOR_MARKER, COMMAND_POST_MARKER) must match what `action_install_entry_points()` writes. A mismatch means re-runs append instead of update.
- `action_morph_memex()` renames the source memex directory to `*.pre-gator/` — it does not delete it. Pre-gator dirs are preserved on the branch for PI review. The function prompts for confirmation before any filesystem change; do not add a second prompt inside it.
- `memex-lint.sh` is not executed by any other script. It is a standalone diagnostic tool. Do not import or source it.

## Connections

-> [scripts-core-library](scripts-core-library.md) — CURRENT_GENERATION constant, add_dashboard_repo (dashboard registry), normalize_path, resolve_thin_link
-> [scripts-repo-lifecycle](scripts-repo-lifecycle.md) — gator-update.py for subsequent overlay updates; gator-init.py for per-repo boot display
-> [scripts-cross-cutting](scripts-cross-cutting.md) — gator_core import convention
-> [Index](INDEX.md)
