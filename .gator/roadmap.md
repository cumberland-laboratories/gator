# Roadmap

_Updated 2026-09-14._ Current strategy, priorities, and planned work.

**Retention standard**: this file holds current-facing strategy,
priorities, and planned work. It does NOT accumulate
shipped-release narratives or serve as a change log — Git history
and commit messages are authoritative for what has shipped. Older
shipped-release detail lives at
[`artifacts/2026-09-14-roadmap-shipped-history-archive.md`](artifacts/2026-09-14-roadmap-shipped-history-archive.md).
Soft cap: keep this file under ~250 lines. If it grows past that,
compact or archive before adding.

**Latest released version**: v2.13.2 (2026-09-12) — three
consecutive fully first-try green pipelines (v2.13.0/.1/.2).
**Cumberland HTML style Sketch 2 arc closed 2026-09-14** — 18
commits, three days, closure via bounded positive-policy pivot;
ships whenever the next release cuts. See the shipped-history
archive for detail.

**Status key**: Done · Building · Designed · Considering · Deferred

---

## Product

One product: **Gator** — Git-native governance for AI-assisted
engineering. Ships as `pipx install gator-command`. Open source
under Apache License 2.0. Public monorepo
`github.com/cumberland-laboratories/gator`.

Gator includes local repo governance, pre-commit enforcement,
dashboard, CLI, and gator loop. **Enterprise capabilities**
(transcripts-first evidence custody across Claude + Codex + Gemini,
API-first fleet management, centralized policy) are an optional
layer — same codebase, activated by configuration. The audit
surface (v2.7.0 + v2.8.0) makes Enterprise **evaluator-ready**:
the five canonical audit questions answer correctly against real
multi-vendor custody. Enterprise-cli install remains
source-checkout-only; the single-pipx install path is the public
announcement blocker.

## Strategic Direction

- Open source distribution (Apache 2.0) for both the core CLI and
  Enterprise capabilities.
- Maximum developer adoption through frictionless installation.
- Dashboard-first product surface — CLI commands become internal
  implementation details.
- Multi-agent governance — gator loop as the foundation for
  governed AI collaboration.

## Current Priority

Architect-set 2026-08-17, updated 2026-09-14 after the Cumberland
arc closure. The two structural priorities from that reset
(machine-scoped runtime; Blueprints 2.0 Release A) both shipped
(v2.9.0 and v2.12.0 respectively), so the stack has advanced.

1. **Gator + Enterprise: polished and ready for lots of users.**
   Two halves of one readiness goal.
   - **(a) Gator general polish** — ridiculously easy to install
     and use: Dashboard-first UX, one-command install, zero-config
     governance; every rough edge in install/onboard/update is a
     priority bug. See "Building — Priority 1: Post-Install
     Onboarding & UX" below plus the open operational items in
     `inbox.md` (stale `gator-approve.py` path in pre-commit
     block message, `gator-approve.py --help` broken,
     `gator kill dashboard` UX, stale-Dashboard-in-browser
     detection, etc.). Vaulted-docs rewrite for the pipx-first
     world is an open inbox item since 2026-08-02.
   - **(b) Enterprise at "polished demo" level** — audit surface
     is evaluator-ready; getting to polished-demo means the
     packaging + operability arc: **single-pipx install (the
     announcement blocker)**, cross-OS blob-store defaults,
     bundled pre-commit sync, session-block retirement,
     fresh-machine bootstrap, plus the CLI-output quality tail.
     See "Enterprise — open post-2.6 candidate work" below.

2. **Blueprints 2.0 — HTML inspection surfaces for the human
   Architect.** Interactive HTML blueprints that let the Architect
   navigate the codebase the way an effective AI model does —
   charter-first, progressive-disclosure. The design basis is the
   four-level progressive-disclosure model: **Level 1** charter
   map → **Level 2** charter → covered files/surfaces → **Level 3**
   architecturally-significant functions (curated) → **Level 4**
   drift map (charter-declared vs code-observed structure).
   Release A shipped v2.12.0 (artifact-first HTML protocol +
   two templates + reference impl). **Release B (feature-blueprint
   generation procedure) is the next increment.** See "Building —
   Priority 2: Blueprints 2.0" below.

3. **Gator Loop: smooth the rough edges.** All 12 subcommands
   shipped in v2.1.0; what remains is Dashboard integration
   (events timeline, session card) and protocol refinements from
   real usage. GitHub umbrella
   [#5](https://github.com/cumberland-laboratories/gator/issues/5)
   with children #6/#7/#8. See "Building — Priority 3: Gator Loop
   Polish" below.

4. **Normalized transcript index (exploratory, below Loop).**
   Optional, rebuildable message/tool-call index layer over
   Enterprise transcript custody — raw blob stays source of truth.
   Design note:
   `vault/artifacts/2026-08-17-gator-normalized-transcript-index-design-note.md`.

---

## Building — Priority 1: Post-Install Onboarding & UX

The `.exe` installer is deferred — the target audience (developers
using AI tools) has Python and CLI fluency. The real gap is what
happens after `pipx install gator-command`. The v2.4.x train
collapsed the install/update surface into a much simpler shape
(update in place, no `gator-install` branch, dedicated
`/api/repo/<name>/gatorize` endpoint, unconditional `cli-version`
stamps, honest recovery messaging).

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **First-run welcome screen** | Considering | Empty fleet → welcome with "Add Repo" + "Gatorize" prominently, not empty table |
| 2 | **Getting-started documentation** | Considering | Linear path: install → dashboard → add repo → gator init → first commit → see result. Complements shipped `docs/custom-skills-and-team-workflow.md` |
| 3 | **In-dashboard next-step guidance** | Considering | After adding a repo, show "Open your AI CLI and type gator init" hint |
| 4 | **Server reuse detection** | Considering | `gator dashboard` finds running instance instead of starting duplicate |
| 5 | **Branding consistency** | Considering | Clean up any stale "Gator" vs "Gator Desktop" vs "Gator Dashboard" inconsistencies in docs |

## Building — Priority 2: Blueprints 2.0

HTML-format blueprints designed for the **human Architect** to
navigate the code and functions — externalizing the charter-first
understanding heuristic (orient → localize → verify → expand →
reconcile → decide) into a progressive-disclosure exploration
surface. HTML is the right medium: progressive disclosure, local
exploration without a heavy app surface, natural fit with the
Dashboard/file-browser direction.

**Supporting artifacts** (vault, machine-local):
[starter experiment](vault/blueprints/charter-flowchart-high-level.html)
· [architect inspection exploration](vault/artifacts/2026-08-09-charter-flowchart-architect-inspection-exploration.md)
· [charter-first understanding heuristic](vault/artifacts/2026-08-14-charter-first-code-understanding-heuristic.md)
· [charters vs module guides delta](vault/artifacts/2026-08-12-charters-vs-module-guides-delta.md)
· [charter origin story](vault/artifacts/2026-08-12-charter-origin-story-parnas-dijkstra-module-guides.md).

Release A shipped v2.12.0 (artifact-first HTML protocol + two
shipped templates + reference impl). Release B is the next
increment.

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **Release B — feature-blueprint generation procedure** | Considering | Next Blueprints 2.0 increment. Generate feature blueprints from charters + INDEX.md. Location: Dashboard view vs `.gator/blueprints/`. |
| 2 | **Level 2 — Charter → covered surfaces drill-down** | Considering | Expand a charter cluster into files/scripts/CLI surfaces/artifact boundaries. Suggested starting cluster: `repo-lifecycle` or `fleet-intelligence`. |
| 3 | **Level 3 — Function map (curated)** | Considering | Architecturally significant functions only — public/orchestrator functions, meaningful seams, tripwire + "does not own" surfaces. NOT an every-helper graph. |
| 4 | **Level 4 — Drift map (charter vs code)** | Considering | Compare charter-declared structure against code-observed structure; surface mismatches as inspection prompts, not verdicts. Likely the most strategically valuable level. |
| 5 | **Relationship-type distinction** | Considering | Visually separate runtime / governance / packaging / conceptual edges. |

## Building — Priority 3: Gator Loop Polish

Shipped in v2.1.0: `wait`, `pause`, `interject`, `end`,
round-versioned artifacts, architect token, dashboard loop
sidebar. What remains is refinement from real usage.

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **Loop dashboard events timeline** | Designed | Render `events.jsonl` as formatted timeline table instead of raw JSON. [Plan](artifacts/2026-07-27-loop-usability-implementation-plan.md) |
| 2 | **Loop dashboard session card** | Considering | Summary card showing loop stage, rounds, join status on Repo overview |
| 3 | **Loop protocol refinement** | Considering | Update protocol and artifact formats based on live trial learnings |
| 4 | **Auto-trigger update after migration** | Considering | `--migrate-layout` could auto-run `gator update` to refresh scripts |

## Considering

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **SonarCloud integration** | Considering | Code quality gates for the public repo |
| 2 | **Branch switching in Repo view** | Considering | Replace static branch label with dropdown |
| 3 | **MCP server** | Considering | Interesting surface for AI tool integration |
| 4 | **Audit view visualizations** | Considering | Session timeline, decision density, file heat map |
| 5 | **Legacy Memex retirement** | Considering (charter-side done 2026-08-16) | Cognitive cleanup of large legacy surface; vault-archive disposition + fleet-repo Memex structures remain |

## Deferred

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | **Codex model name canonicalization** | Deferred | Quality cleanup for session identity |
| 2 | **In-flight session visibility** | Deferred | Sessions only visible after first commit |
| 3 | **enforcer-review.py split** | Deferred | Architectural hygiene |

---

## Enterprise — open post-2.6 candidate work

The audit-surface tranche (Q1-Q5 across Claude + Codex + Gemini)
completed with v2.8.0. What remains open below is the arc toward
a defensible public Enterprise announcement (single-pipx install
is the blocker), the quality tail, and the exploratory transcript
index.

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 3 | **Enterprise-cli bundled `gator-pre-commit.py` sync** | Considering | Bundled copy doesn't carry the change-type (v2.5.3) or significance (v2.6.0) enum gates. Byte-identity relaxed by MVP plan §D2; drift is a real gap for Enterprise-provisioned repos on first commit. |
| 4 | **Enterprise-side session-block retirement** | Considering | Post-2.6 Enterprise cleanup. Inert-but-in-tree code paths across `block_generate.py`, `bundled_scripts/gator-session-block.py`, `services/session_blocks.py`, `routes/session_blocks.py`, `routes/crypto.py`, `models/evidence_block.py`, dispatcher `blocks` verb. Bulk deletion. |
| 5 | **Single-pipx install path** | Considering | `pipx install "gator-command[enterprise]"` or `pipx install gator-enterprise-command`. **Blocks a public Enterprise announcement.** |
| 6 | **Cross-OS blob-store defaults** | Considering | `BLOB_STORE_ROOT` default (`/var/lib/gator-enterprise/blobs`) is POSIX; crashes on Windows without manual override. Needs OS-aware default or a documented containerized reference. |
| 7 | **Fresh-machine bootstrap smoke test** | Considering | Current smoke assumes venv + Postgres + machine-id pre-exist. Truly-fresh-machine protocol needs venv + Postgres install + first bootstrap on Windows/macOS/Linux. |
| 8 | **v1 `active-vendor-session.json` compat decision** | Considering | Two `xfail(strict=False)` tests in v2.6.0. Either implement v1 read-shim or delete the tests if v1 is truly out of support. |
| 16 | **`transcripts pull` content-hash skip** | Considering | Pull loop is stateless; every pull re-reads/re-gzips/re-uploads EVERY discovered transcript. Fix: content-hash handshake — sha256 local files, fetch machine's known hash map, skip on match. Preserves evidence-integrity property; makes unchanged files cost a local hash instead of an upload. Cost class: S-M. |
| 17 | **Enterprise CLI output polish pass** | Considering | Cosmetic/verify observations from Phase 2 + Phase 6 smoke campaigns (per-page `By vendor:` summary, `Model -` on stub sessions, pagination-hint dash inconsistency, Gemini `started_at` on old sessions, em-dash Windows encoding, cumulative pagination count, oldest-first `--limit` order). All non-blocking. Cost class: S. |
| 18 | **Normalized transcript index (exploratory)** | Considering | Optional additive tables (`transcript_messages` + `transcript_tool_calls`) hanging off `transcript_session_id` — turn-level queries. Hard constraint: raw blob stays source of truth; index is additive, rebuildable, safe to discard/regenerate. Design note in vault. Priority below Gator Loop. |

## What Enterprise adds

Enterprise capabilities build on top of the core Gator install —
they don't replace anything. The activation surface is `gator
enterprise` as a CLI subcommand group:

```
gator enterprise activate     — one-time machine setup (creates ~/.gator/enterprise/, installs global git hooks, registers machine)
gator enterprise sync         — pull hook-policy and org policies from Enterprise
gator enterprise repo init    — provision a repo for Enterprise governance
gator enterprise transcripts  — pull/list/show/get/link session transcripts (--vendor claude|codex|gemini)
gator enterprise commits transcripts <sha>   — Q1: which transcripts touched this commit
gator enterprise commits list --repo <id>    — Q2: which recent commits have transcript coverage
gator enterprise transcripts list --unlinked — Q3: which recent transcripts are still unlinked
gator enterprise commits provenance <sha>    — Q4: which machine produced this commit
gator enterprise repos transcripts <id>      — Q5: which vendor sessions touched this repo over time
```

Same install, same CLI, same repo. Enterprise adds:

- Session evidence capture and storage
- Fleet-scale audit and reporting
- Centralized policy management
- Git provider integrations (GitHub App, webhooks)
- API-first fleet visibility

---

## Connections

- [Mission](mission.md) — what we're building and why
- [Shipped-history archive](artifacts/2026-09-14-roadmap-shipped-history-archive.md) — versions, features, dates
- [Product split](artifacts/2026-06-22-gator-individual-vs-enterprise-product-split.md) — boundary decision
- [Monorepo convergence plan](artifacts/2026-07-16-monorepo-convergence-plan.md) — merge assessment + execution plan
- [Loop usability plan](artifacts/2026-07-27-loop-usability-implementation-plan.md) — wait, artifacts, dashboard visibility
- [Architect authority plan](artifacts/2026-07-26-architect-loop-authority-plan.md) — pause, interject, end
- [`.includes/` migration sketch](artifacts/2026-07-27-gator-content-vs-includes-migration-implementation-sketch.md) — v2 layout design
- Vault plan chains (gitignored, machine-local) — transcripts-first MVP + v2.6.0 stabilization; non-Enterprise session cleanup; machine-scoped runtime; Blueprints 2.0 supporting artifacts; Enterprise audit-surface tranche; Dashboard UI arc; Cumberland HTML style Sketch 2.
