# Procedure: Committing `.gator/` Files After a Gator-Driven Modification

**Audience**: AI models working in a Gator-governed repo after `gator update`, `gator gatorize`, or any command that Gator itself uses to modify `.gator/` content. Also applies to routine session work where `.gator/` files change as part of the governance loop.

**Symptom that triggers this procedure**: `git status` shows modified or new files under `.gator/`, and you (the agent) are unsure whether they should be committed, whether they are governance residue, or whether they are the operator's manual work-in-progress.

**Short answer**: **most `.gator/` files SHOULD be committed** when Gator itself changed them. The exceptions are enumerated below and are narrow.

## 1. Default: commit `.gator/` changes that Gator produced

When a Gator command (`gator update`, `gator gatorize`, `gator init`, etc.) modifies tracked `.gator/` files, those modifications ARE the shipped policy propagating into this repo. They must be committed so:

- The repo's `.gator/` state stays in sync with the shipped policy version.
- Other collaborators on the same repo see the same governance surface.
- Fleet-scale drift detection (via `gator-drift.py`) works correctly.
- The `.gator/.gator-version` marker and any updated shipped content stay coherent as a single unit.

**Do not hesitate**: `gator update` producing dozens of `.gator/.includes/` file changes is expected and correct. Stage them and commit them.

## 2. Exceptions — do NOT commit these

The following `.gator/` files are gitignored by design AND/OR are session-local residue that must not be committed:

### 2a. `.pre.gator*` backups from v1→v2 layout migration

Never commit these. They are local rollback backups from `gator update --migrate-layout`. See [`pre-gator-residue.md`](pre-gator-residue.md) for the vault-recommended handling.

### 2b. `.gator/vault/`

Vault is gitignored by design. Nothing in `.gator/vault/` is committed. If you see something in vault that you think should be tracked, it belongs somewhere else (`.gator/artifacts/`, `.gator/threads/`, `.gator/blueprints/`, etc.) — flag to the Architect for the classification decision, don't move it yourself.

### 2c. Post-commit governance residue

`.gator/commit_draft.md` and `.gator/whiteboard.md` may appear modified after a successful `git commit` — Gator's post-commit hook intentionally resets/clears them. This is expected. Do NOT re-commit them just because they show as modified. See [`../reference-notes/expected-governance-residue.md`](../reference-notes/expected-governance-residue.md).

### 2d. Session snippets from unrelated sessions

`.gator/session-snippets/*.json` files ARE committed as part of the transcripts-first evidence trail — one snippet emitted per commit. That is the normal flow. However, if you see a snippet in the working tree that does NOT correspond to a commit YOU are about to make (e.g. an untracked snippet from a prior session that wasn't caught by that session's commit), the correct handling is to let the NEXT `git commit` sweep it up naturally via the post-commit hook — do not manually stage or commit it as its own artifact.

### 2e. Machine-local operational state

Content that describes the operator's specific machine setup (Postgres port, venv path, one-shot admin tokens, machine-id UUIDs) belongs in `.gator/inbox.md`'s "Machine state" section (which IS committed for shared operational reference) OR in gitignored files like `.env-enterprise-local`. If you produce content that is unambiguously machine-local (a debug log, a scratchpad note), place it in `.tmp/` (gitignored) or the vault (gitignored), never in a tracked `.gator/` file.

## 3. Practical decision procedure

When you see `.gator/` changes in `git status`, walk this ladder:

1. **Is any of the changed content a `.pre.gator*` file?** → vault it per [`pre-gator-residue.md`](pre-gator-residue.md), do NOT commit.
2. **Is the ONLY change `.gator/commit_draft.md` and/or `.gator/whiteboard.md` right after a successful commit?** → expected residue, do NOT re-commit. See [`../reference-notes/expected-governance-residue.md`](../reference-notes/expected-governance-residue.md).
3. **Did `gator update` or another Gator command just run and produce these changes?** → commit them. They ARE the shipped policy propagating. Use `change-type: governance` if the change is purely `.gator/` content that Gator itself updated.
4. **Are the changes a mix of `.gator/` content + code files you edited this session?** → normal commit flow. The `.gator/` charter updates + `commit_draft.md` population + code changes all ride together per the constitution's Loop steps 5-8.
5. **Do you see changes you don't recognize?** → do NOT auto-stage or auto-commit. Ask the Architect to explain what produced them.

## 4. Common failure modes without this procedure

Absent this guidance, models frequently:

- Ask the operator "should I commit these Gator files?" for what should be a trivial yes — wastes operator attention on routine flow.
- Stage `.pre.gator*` files alongside real work — pollutes commits with rollback backups.
- Re-commit `commit_draft.md` after every commit thinking the empty stub is a bug — creates commit noise.
- Try to "clean up" vault contents thinking they should be tracked — moves local-only content into Git.
- Skip committing `gator update` residue because the changes look mysterious — repo drifts from shipped policy.

## 5. Related surfaces

- [`pre-gator-residue.md`](pre-gator-residue.md) — the specific `.pre.gator*` case.
- [`../reference-notes/expected-governance-residue.md`](../reference-notes/expected-governance-residue.md) — the post-commit `commit_draft.md` + `whiteboard.md` rotation.
- The [constitution](../constitution.md)'s "The Loop" section — normative source for when charter updates + `commit_draft.md` writes + `git commit` happen together.
