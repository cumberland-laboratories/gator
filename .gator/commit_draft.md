---
message: "Loop: reviewer-gated Architect plans and revision planning loops (#51)"
change-type: feature
significance: notable
decision-tags: [loop, planning, provenance, dashboard, governance]
agent: claude-opus-5-5
architect: Alan Gillette
---

# Session Change Log

- **Checkpoint 1: Architect-originated plan entry (#51).**
  - **Start:** `gator loop start --plan-file P [--sketch S]` starts a planning loop from an Architect-supplied plan.
  - **Input checks:** the plan is read once through the new `read_governed_input` (repo containment, no links or aliases, regular, stable, UTF-8, at most 256 KiB) and validated by the SAME `_check_plan_draft` as a Draftor draft.
  - **Storage:** it is stored as immutable `architect-plan.md` plus `plan.round-0.md` and `plan.current.md`. The loop starts at the existing `plan_review` stage with the Reviewer acting first, records one Architect `initial_plan` turn and no Draftor turn, and emits `architect_plan_submitted`.
  - **Approval:** findings hand the plan to the Draftor for a full replacement; only Reviewer approval makes it a coding-loop source.
  - **Verifier:** the new generic verifier (`verify_fixed_artifact`, a closed allowlist with per-name limits) replaces brief-only verification; the brief functions are brief-scoped wrappers with unchanged results.
  - **Provenance:** a `planning_source()` accessor, status/JSON provenance lines, Reviewer/Draftor prompts and a protocol "Planning Sources" section.
  - **Tests:** new `tests/test_loop_plan_sources.py`.
  - **Charters:** `scripts-loop.md` (new entries, Architect-plan TRIPWIRE), `scripts-cross-cutting.md`.
- **Checkpoint 2: revision planning from an approved loop (#51).**
  - **Start:** `gator loop start --sketch S --revise-from <approved planning loop>` creates an ordinary Draftor-led planning loop.
  - **Baseline copies:** under the source's session lock (read-only), it identifies the approving review (the last Reviewer "Plan approved" turn, byte-equal to `findings.current.md`) and the approved plan (`plan.current.md`, byte-equal to the latest plan submission). It copies both as immutable, digest-verified `revision-baseline-plan.md` / `revision-baseline-approval.md`, and records a `revision` block.
  - **Source loop:** never written; the copies stay valid if it is removed.
  - **Failures:** a missing or inconsistent approval, unapproved or coding sources, an outside-repo sketch, and conflicting flags all fail atomically with a named reason.
  - **Participant wording:** status lines, the Draftor first-turn prompt and the protocol revision paragraph.
  - **Tests:** checkpoint-2 tests in `tests/test_loop_plan_sources.py`.
  - **Charters:** `scripts-loop.md` (Revision Baselines TRIPWIRE), `scripts-cross-cutting.md`.
- **Checkpoint 3: Dashboard creation and inspection of plan sources (#51).**
  - **Server:** `POST /loops/start` accepts `plan_path` or `revise_from`, with type and conflict checks, and passes lexical paths to `init_loop`, which is the only validator. Strict `planning_source` / `plan_source` / `revision` status views; three fixed artifact names in the allowlist; provenance pointer lines in `/prompt`; `planning_source` on `/loops` items.
  - **UI:** a "Plan source" choice in the create form (sketch, revise an approved plan, Architect plan for review); the provenance source line; provenance-first artifact order with plain-word labels and integrity text; the Architect-plan timeline label; the coding-loop feature prefill (empty fields only, editable).
  - **Tests:** Dashboard API (`TestPlanSources51`) and focused Playwright tests.
  - **Charters:** `scripts-dashboard.md`, `scripts-dashboard-ui.md`, `scripts-cross-cutting.md`.
