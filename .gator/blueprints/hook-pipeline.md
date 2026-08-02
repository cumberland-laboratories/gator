# Hook Pipeline

## What This Page Is

This page explains how the pre-commit and post-commit hooks work across all three repo types: gator-command (this source repo), the deployed gator public clone, and gatorized fleet repos.

The hooks are the governance enforcement boundary. Understanding where they run, what code they execute, and how the copies stay synchronized prevents the most dangerous class of Gator bugs: silent governance bypass.

## Why This Exists

The same hook logic exists in multiple locations:

- `.gator/scripts/gator-pre-commit.py` in this repo (self-governance)
- `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py` (the template)
- `gator-engine/templates/gator-starter/scripts/gator-pre-commit.py` (deployed template)
- `.gator/scripts/gator-pre-commit.py` in every fleet repo (installed copy)

These must be byte-identical (or close). Drift between copies means different repos get different enforcement, which undermines the governance claim.

→ charter: [cross-cutting](../charters/scripts-cross-cutting.md) (template sync tripwire)

## The Three-Phase Hook Architecture

Every repo with Gator hooks runs the same three-phase pipeline on `git commit`:

```
Phase 1: validate (pre-commit hook)
    gator-pre-commit.py --phase validate
    │
    ├── read enforcement level from .gator/config.json
    │   → _read_enforcement_level()
    │   "off" → clear stale artifacts, exit
    │
    ├── parse commit_draft.md (YAML frontmatter + body)
    │   → parse_commit_draft()
    │
    ├── check override (PI-approved bypass)
    │   → check_override()
    │
    ├── hard rules (block on failure)
    │   → validate_hard_rules()
    │   • charter-alongside-code
    │   • charter-index-gap
    │   • empty commit_draft
    │   • frontmatter parse error
    │
    ├── soft rules (warn only)
    │   → validate_soft_rules()
    │   • no-significance, no-decision-tags
    │   • tripwire-touched, high-file-count
    │   • stale-charter-refs, new-functions-undocumented
    │
    ├── Layer 1 lint (dangerous code patterns)
    │   → run_layer1_lint()
    │   • SEC-001/002/003 (passwords, API keys, private keys)
    │   • SQL dangers, eval(), shell injection
    │   • self-excludes (basename) + doc excludes (path-scoped)
    │   • _effective_severity() context-aware downgrade
    │
    ├── "warn" mode → convert failures to warnings
    │
    ├── write status.json, whiteboard.md, commit_issues.md
    │   → build_status(), write_status_json(), write_whiteboard()
    │
    └── exit 0 (pass) or exit 1 (block)

Phase 2: trailers (commit-msg hook)
    gator-pre-commit.py --phase trailers
    │
    ├── parse commit_draft.md again
    ├── assemble Gator-* trailers from frontmatter + .gator/ state
    │   → assemble_trailers()
    │   • Gator-Metrics, Gator-Change-Type, Gator-Significance
    │   • Gator-Decision-Tags, Gator-Agent, Gator-Architect
    │
    └── append trailers to commit message

Phase 3: cleanup (post-commit hook)
    gator-pre-commit.py --phase cleanup
    │
    ├── append commit to rolling active session file
    │   → append_active_session_entry()
    │
    └── reset commit_draft.md to blank stub
```

→ charter: [commit-gate](../../.gator/charters/commit-gate.md) (full function inventory)
→ blueprint: [commit-pipeline](commit-pipeline.md) (broader commit flow context)

## How Hooks Differ by Repo Type

### gator-command (this repo)

**Hook location:** `.git/hooks/pre-commit`, `commit-msg`, `post-commit`
**Script:** `.gator/scripts/gator-pre-commit.py`
**Charter domain:** Resolves via `resolve_charter_surface()`. Detects two domains:
- `.gator/charters/` (self-governance — commit-gate, gator-core, etc.)
- `.gator/charters/` (product — scripts-installer, scripts-dashboard, etc.)

The hook requires charters from BOTH domains when code in `src/gator_command/scripts/` changes. This is why commits to product scripts trigger `scripts-*` charter requirements.

→ charter: [cross-cutting](../charters/scripts-cross-cutting.md) (charter surface resolution)

**Enforcement:** `.gator/config.json` → `enforcement_level`. This repo runs `strict`.

**Template sync obligation:** After editing `.gator/scripts/gator-pre-commit.py`, copy to `src/gator_command/templates/gator-starter/scripts/`. After editing the template, copy back. Divergence breaks fleet enforcement.

→ charter: [cross-cutting](../charters/scripts-cross-cutting.md) (template sync tripwire)

### gator public clone (deployed)

**Hook location:** `.git/hooks/pre-commit`, `commit-msg`, `post-commit`
**Script:** `.gator/scripts/gator-pre-commit.py` (installed by deploy into `.gator/`)
**Charter domain:** Single domain — `.gator/charters/` only. No `.gator/charters/` in the deployed repo (those are source-repo product charters).

The deployed repo has minimal charter scaffolding (INDEX.md with empty table). The hooks enforce charter-alongside-code but there are few charters to trigger against. This is intentional — the deployed repo is a command post, not a code project.

**Enforcement:** `.gator/config.json` if present, otherwise defaults to `strict`.

**Template source:** The hooks in `.gator/scripts/` come from `gator-engine/templates/gator-starter/scripts/` during deploy. They are refreshed on each deploy.

### Gatorized fleet repos

**Hook location:** `.git/hooks/pre-commit`, `commit-msg`, `post-commit`
**Script:** `.gator/scripts/gator-pre-commit.py` (installed by `gator gatorize`, refreshed by `gator update`)
**Charter domain:** Single domain — `.gator/charters/` only.

**Hook installation:**
- `install_hooks()` in `gatorize-actions.sh` copies hook wrappers from template
- On Windows (MSYS/Git Bash): `write_windows_hook()` generates direct-Python-shebang wrappers instead of copying bash scripts
- Existing non-Gator hooks backed up with `.pre-gator` suffix
- Idempotent — existing Gator hooks overwritten silently

→ charter: [scripts-installer](../charters/scripts-installer.md) (install_hooks)

**Enforcement:** `.gator/config.json` → `enforcement_level` (strict/warn/off). Configurable via `gator-enforce.py` CLI or dashboard Settings view.

**Template refresh:** `gator-update` (Channel 1) overlays scripts from the gator clone's template directory. Hook wrappers in `.git/hooks/` are also refreshed by `install_git_hooks()` in `gator-update.py`.

→ charter: [scripts-repo-lifecycle](../charters/scripts-repo-lifecycle.md)

## The Self-Containment Invariant

`gator-pre-commit.py` does NOT import `gator_core.py`. It has its own `git()`, `find_gator_root()`, `count_charters()`, etc. This is intentional — the commit gate must work with zero import dependencies beyond stdlib. A broken import path means broken commits across the entire fleet.

If you add a function to `gator_core.py` that the pre-commit hook could use, do NOT refactor the hook to import it.

→ charter: [cross-cutting](../charters/scripts-cross-cutting.md) (self-containment tripwire)
→ charter: [commit-gate](../../.gator/charters/commit-gate.md)

## Key Invariants

1. **Template and self-governance copies must stay synchronized.** `.gator/scripts/gator-pre-commit.py` (self-governance) and `src/gator_command/templates/gator-starter/scripts/gator-pre-commit.py` (template) — edit one, copy to the other.

2. **The hook is self-contained.** No imports from `gator_core.py`. Stdlib only. This is a trust boundary.

3. **Phase 2 (trailers) is deterministic.** Same inputs → same trailers. No LLM, no nondeterminism. The trailer integrity is part of the product claim.

4. **Enforcement level is per-repo.** Read from `.gator/config.json` at the top of Phase 1. `off` clears stale artifacts before exiting.

5. **Windows hooks are generated, not copied.** `write_windows_hook()` bakes in the Python path at install time. Behavior must match the bash wrappers.

## Connections

→ blueprint: [repo-topology](repo-topology.md) — the three repo types this hook runs in
→ blueprint: [commit-pipeline](commit-pipeline.md) — the broader commit flow
→ charter: [commit-gate](../../.gator/charters/commit-gate.md) — full function inventory for the hook
→ charter: [cross-cutting](../charters/scripts-cross-cutting.md) — template sync, self-containment, charter surface
→ charter: [scripts-installer](../charters/scripts-installer.md) — hook installation
→ charter: [scripts-repo-lifecycle](../charters/scripts-repo-lifecycle.md) — hook refresh via update
