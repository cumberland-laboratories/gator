# Procedure: `.pre.gator*` Residue After a v1→v2 Upgrade

**Audience**: AI models working in a Gator-governed repo that has recently undergone a `gator update --migrate-layout` v1→v2 layout upgrade.

**Symptom that triggers this procedure**: you see files or directories named with the `.pre.gator-*` prefix in the working tree — e.g. `.pre.gator-update-<timestamp>/`, `.pre.gator-<filename>.bak`, or similar. You are unsure what they are, whether they should be committed, and whether it is safe to touch them.

## 1. What these files are

They are **safety-net backups** written by `gator update` (specifically the `migrate_layout()` step in `gator-update.py`) before it modifies or moves shipped `.gator/` content into the v2 layout (`.gator/.includes/`). The suffix `.pre.gator-*` marks "this is what the file / directory looked like BEFORE Gator touched it during the update."

Their purpose is rollback — if the migration produced unexpected results, the operator can restore from the `.pre.gator-*` copy. That is the entire load-bearing function of these files.

## 2. What they are NOT

- They are **NOT** part of the current governance model. Nothing in the active codebase reads them.
- They are **NOT** meant to be committed to Git. They are local-machine artifacts.
- They are **NOT** documentation, examples, or reference material. Do not cite them or link to them from committed content.
- They are **NOT** a signal that the update is incomplete. A successful `gator update` produces these files by design.

## 3. What to do with them

**Recommended: move to vault.** The vault (`.gator/vault/`) is the correct home for local-only, gitignored, rollback-relevant material.

```
.gator/vault/pre-update-backups/<YYYY-MM-DD>/<original-path-preserved>/
```

Concrete steps for an agent asked to clean up `.pre.gator*` residue:

1. Confirm with the Architect that the v1→v2 upgrade completed successfully — the working tree behaves normally, tests pass, `gator init` boot sequence surfaces no drift indicator.
2. Create the vault subdirectory if it doesn't exist: `.gator/vault/pre-update-backups/<date>/`.
3. Move each `.pre.gator*` file or directory into it, preserving the original relative path under the date-stamped subdirectory. For example, `.gator/procedures/.pre.gator-update-charter-alignment.md` moves to `.gator/vault/pre-update-backups/<date>/procedures/pre.gator-update-charter-alignment.md`.
4. Do NOT delete the moved copies during this pass. The vault is where they live until the operator decides to clear them.

**When to delete from vault**: after ~30 days of stable operation on the v2 layout with no rollback needed. That is the operator's call, not the agent's. If asked to delete `pre-update-backups/`, verify the operator confirmed the ~30-day window has passed and that they own the risk.

## 4. Explicit non-actions

- Do NOT `git add` any file matching `**/.pre.gator*`. If you see one staged, unstage it.
- Do NOT modify the contents of a `.pre.gator*` file to "fix" what looks like outdated content. That defeats their rollback purpose.
- Do NOT delete `.pre.gator*` files without vaulting first (unless the Architect has explicitly authorized skipping vault and doing an immediate delete).
- Do NOT confuse `.pre.gator*` with active `.gator/` content. If you are unsure whether a specific file is one or the other, name it back to the Architect and ask.

## 5. Discovery checks

If you are opening a session and want to know whether this procedure applies:

```bash
find .gator -name ".pre.gator*" -maxdepth 4 2>/dev/null | head -20
find . -maxdepth 2 -name ".pre.gator*" 2>/dev/null | head -20
```

Zero output = no residue, nothing to do. Non-zero output = residue present; apply this procedure.

## 6. Why this procedure exists

Models unfamiliar with Gator's v1→v2 migration semantics reliably get confused by `.pre.gator*` files. Common failure modes without this procedure:

- Agent proposes to `git add .pre.gator*` alongside real work — pollutes commits.
- Agent proposes to `rm -rf .pre.gator*` without preserving the rollback — removes safety net.
- Agent treats `.pre.gator*` content as authoritative and cross-references it from new documentation — cites a snapshot of retired behavior.
- Agent stops mid-task to ask the operator what these files are on every session, wasting the operator's attention.

The vault-recommended path (§3) resolves all four failure modes: safety preserved, tree cleaned, no risk of accidental commit, no future model confusion.

## 7. Related surfaces

- [`reference-notes/expected-governance-residue.md`](../reference-notes/expected-governance-residue.md) — post-commit residue (`commit_draft.md` + `whiteboard.md`), a DIFFERENT case from `.pre.gator*` upgrade residue. Do not confuse the two.
- [`procedures/committing-gator-files.md`](committing-gator-files.md) — general guidance on which `.gator/` files to commit after any Gator-driven modification (including `gator update`). `.pre.gator*` is the explicit exception documented there.
