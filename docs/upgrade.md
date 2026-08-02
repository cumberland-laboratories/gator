# Upgrade & Versioning

## Version Scheme

Gator uses semantic versioning: `MAJOR.MINOR.PATCH`

- **Major** — breaking changes to governance contracts (constitution format, charter format, trailer keys)
- **Minor** — new features, new commands, new extraction support
- **Patch** — bug fixes, documentation improvements

The current version is always available via:

```bash
python gator-engine/scripts/gator-version.py
```

## Version Resolution

Gator resolves its version in this order:

1. **Git tags** — `git describe --tags` (authoritative in development)
2. **VERSION file** — `VERSION` at repo root (authoritative in deployed repos)
3. **Git hash** — bare commit hash as fallback
4. **"dev"** — no git, no VERSION file

## Upgrading the Command Post

Pull product updates from Cumberland's upstream:

```bash
git fetch upstream
git checkout upstream/main -- gator-engine/
git add gator-engine/
git commit -m "Update gator-engine to v1.1.0"
```

Your knowledge layer (`gator-command/`) is untouched. Only product code (`gator-engine/`) is updated.

## Upgrading Fleet Repos

After updating the command post, propagate to each governed repo. `gator update` must run from inside the governed repo (or use `--path` to point at it):

**Single repo:**

```bash
cd /path/to/your/repo
python /path/to/gator/gator-engine/scripts/gator-update.py
```

**Fleet rollout (all registered repos):**

```bash
# From the command post — update every repo in the registry
for repo in $(python gator-engine/scripts/gator-fleet-report.py --json | python -c "
import sys, json
for r in json.load(sys.stdin)['repos']:
    if r.get('path'): print(r['path'])
"); do
    echo "Updating $repo..."
    python gator-engine/scripts/gator-update.py --path "$repo" --dry-run
done
```

Remove `--dry-run` once you've confirmed the plan looks correct.

**What `gator update` does:**

- Template files are overwritten with the latest version
- User content (charters, threads, artifacts) is never deleted
- New files from updated templates are added
- Removed template files are left in place (no cleanup)

Always use `--dry-run` first on at least one repo to preview changes before applying across the fleet.

## Generation System

Gator tracks structural compatibility via a generation number (currently `gen 2`). When a release changes the `.gator/` directory structure, the generation increments.

`gator drift` flags repos on older generations:

```
  ! data-pipeline
    gen 1  |  charters: 0  |  hooks: no
    ⚠ Generation drift. Run gator update.
```

## Checking for Drift

```bash
python gator-engine/scripts/gator-drift.py
```

This compares each fleet repo against current standards and flags:

- Generation mismatches
- Missing or outdated hooks
- Stale policy references
- Charter coverage gaps

## Operational Procedures

### Re-baselining a Drifted Fleet

If multiple repos have drifted (common after an upgrade or a period of rapid development):

1. **Assess the damage.** Run `gator drift --json` to get machine-readable drift status for every repo.
2. **Dry-run first.** Run `gator update --dry-run --path /path/to/repo` on one drifted repo to see what would change.
3. **Update one repo, verify.** Apply the update, run `gator drift` again, confirm the repo is now current.
4. **Roll out to the fleet.** Use the fleet rollout loop above with `--dry-run`, review, then remove the flag.
5. **Verify.** Run `gator fleet-report` and `gator drift` to confirm the fleet is clean.

### Broken Hooks Across Multiple Repos

If pre-commit hooks stop firing (common after Python version changes or path changes):

1. **Diagnose.** Check one affected repo: `ls -la /path/to/repo/.git/hooks/pre-commit`. If the file is missing or points to a stale Python path, that's the issue.
2. **Fix.** Run `gator update` on the repo — it reinstalls hooks using the current Python interpreter.
3. **Fleet fix.** Use the fleet rollout loop to re-run `gator update` across all affected repos. On Windows, hooks are rewritten as Python-native wrappers using the current `sys.executable`, so a Python upgrade requires a fleet-wide `gator update`.

### Remote-Only Repos: What You Get and What You Don't

Repos registered by remote URL (no local checkout) have a different guarantee set:

| Capability | Local repo | Remote-only repo |
|-----------|-----------|-----------------|
| Fleet report | Full (filesystem + git) | Partial (git refs only) |
| Drift detection | Full | Generation + policy version only |
| Trailer extraction | Full | Full (via `git log`) |
| Session summaries | Full (if committed) | Full (if committed, via `git show`) |
| Charter inspection | Full | Via `git show` (no filesystem) |
| Hook status | Verified | Not verifiable |
| `gator update` | Yes | No (needs local checkout) |

For enterprise fleets with repos across multiple machines, remote-only scanning provides governance visibility without requiring local clones. But hook status and direct updates require a local checkout.

### What "Current" Means

A repo is "current" when:

- Its generation matches `CURRENT_GENERATION` in `gator_core.py` (currently `gen 2`)
- Its hooks are installed and point to a working Python interpreter
- Its thin link references a reachable command post
- Its policy version matches the command post's `org-policy.md`

`gator drift` checks all four. A repo that passes all checks is current. A repo that fails any check is drifted, with the specific failure identified in the drift report.

## Migration Notes

### v0.1.0 → v1.0.0

See the full [Changelog](../CHANGELOG.md) for everything in v1.0.0.

- No breaking changes to governance contracts
- New: VERSION file at repo root
- New: MkDocs documentation site
- New: Deployed repos use `gator-engine/` + `gator-command/` separation
- Upgrade path: `git fetch upstream && git checkout upstream/main -- gator-engine/`
