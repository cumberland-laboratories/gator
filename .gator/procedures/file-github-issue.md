# File a GitHub Issue

The canonical workflow for filing an issue on `cumberland-laboratories/gator` and landing it on the Gator project board with correct metadata. Written after the 2026-08-04 migration of `.gator/issues.md` #3 (the first issue on the public repo) established the CLI pattern end-to-end. Every subsequent bug, feature, refactor, packaging chore, docs task, or investigation worth tracking beyond the current session follows this procedure.

## When to use

- A bug surfaces in code that another session (or another contributor) should be able to find and pick up
- A feature scope emerges that needs multi-commit or multi-surface work
- A refactor, packaging chore, or governance change needs a durable work item
- A deadline-driven maintenance task lands (deprecations, license, upstream changes)
- An investigation/spike has a definable question worth returning to

**Do NOT** file a GitHub issue for:
- Ephemeral session state (use `TaskCreate` / TodoWrite)
- Half-formed ideas (use `.gator/inbox.md`; promote to Issue on triage)
- Architectural decisions or design memory (use `.gator/charters/` or `.gator/artifacts/`)
- Commit-message plumbing (use `.gator/commit_draft.md`)

## Prerequisites

- `gh` CLI installed and authenticated
- Token scope includes `project` (for adding to Gator project + setting fields):
  ```
  gh auth refresh -s project
  ```
  This is a one-time interactive OAuth (opens browser). If a `gh project ...` command errors with `authentication token is missing required scopes [read:project]`, this is the fix. Prefix with `!` in the Claude Code prompt to run it in-session.
- Working from a shell where `gh auth status` shows the `cumberland-laboratories` account

## Fixed field/label vocabulary

Do not invent new values without adding them to the Project's field options first (single-select fields reject unknown values via API).

**Labels** (repo-level, `.github/` doesn't manage them — created via `gh label create` on first use):
- `bug`, `enhancement` (built-in)
- `documentation`, `question` (built-in)
- `good first issue`, `help wanted` (built-in — use to invite contribution)
- `dashboard`, `hooks`, `charters`, `loop`, `enterprise`, `packaging`, `release` (Gator-specific — add on first use with `gh label create <name> --color <hex> --description "<what it means>"`)

**Project fields** (single-select, defined on the Gator project — number `1`, owner `cumberland-laboratories`):
- `Priority`: `P0` (drop everything) / `P1` (this release) / `P2` (soon) / `P3` (someday)
- `Area`: `Core CLI` / `Dashboard` / `Hooks` / `Charters` / `Loop` / `Enterprise` / `Packaging / Release` / `Docs`
- `Status`: `Todo` / `In Progress` / `Done`

Rule of thumb: issue type → `Area` and label (usually agree); severity → `Priority`; where it is in the flow → `Status`.

## Steps

### 1. Draft the body to a gitignored file

Write the issue body to `.tmp/issue-<short-slug>-body.md`. Keeps markdown formatting intact when passing to `gh` (avoids shell-escaping hell). `.tmp/` is gitignored, so the draft never accidentally commits.

Structure the body with these sections (adapt as fits — not every section applies to every issue):

```markdown
### Problem
[What the user or maintainer sees. One paragraph, plain-language.]

### Root cause
[What in the code produces the observed behavior. Cite file paths + line numbers where possible.]

### Reproduce
1. [Setup]
2. [Trigger]
3. [Observed]
4. [Contrast with expected]

### Fix path
- [Proposed direction — bullet list, options if multiple]

### Discovered
[Date + context — how it surfaced]

### References
- Any related fix, commit, or docs
- Link back to the originating `.gator/inbox.md` line or prior `.gator/issues.md` entry if migrated
```

### 2. Create any missing labels

If the issue uses a label not yet in the repo, create it first:

```
gh label create <name> --repo cumberland-laboratories/gator \
  --color <6-hex-no-hash> --description "<what it flags>"
```

Colors from the existing set: `bug` red `d73a4a`, `dashboard` green `0e8a16`. Pick colors that read as a family — reserve red/dark-red for severe/urgent, green for surface-visible, blue for docs, purple for advanced/experimental. Consistency helps at-a-glance triage.

### 3. Create the issue

```
gh issue create --repo cumberland-laboratories/gator \
  --title "<one-line-title-under-70-chars>" \
  --body-file .tmp/issue-<slug>-body.md \
  --label bug --label <area-label>
```

Returns the issue URL. Save it — the next steps need it.

### 4. Add the issue to the Gator project

```
gh project item-add 1 --owner cumberland-laboratories \
  --url <issue-url> --format json
```

The JSON output includes an `id` field — the **project item ID** (starts with `PVTI_`). Save it — the field-edit calls need it.

### 5. Discover the project field IDs (one-time)

Field IDs and single-select option IDs are stable for the life of a Project. Cache them the first time — subsequent issue migrations reuse. Discovery command:

```
gh project field-list --owner cumberland-laboratories 1 --format json | python -c "
import json, sys
d = json.load(sys.stdin)
for f in d['fields']:
    if f['name'] in ('Priority', 'Area', 'Status'):
        print(f\"{f['name']}: id={f['id']}\")
        for o in f.get('options', []):
            print(f\"  {o['name']} = {o['id']}\")
"
```

Current values (as of 2026-08-04 — verify with the discovery command if the project is edited):

| Field    | Field ID                            | Option → ID |
|----------|-------------------------------------|-------------|
| Priority | `PVTSSF_lAHOD93k384BfXEKzhZqjO0`    | `P0=08bdccb3`, `P1=d7d930eb`, `P2=d7d8057f`, `P3=0d10bd41` |
| Area     | `PVTSSF_lAHOD93k384BfXEKzhZqkQk`    | `Core CLI=7508c4bc`, `Dashboard=b48957ae`, `Hooks=435fcb50`, `Charters=7be990ad`, `Loop=a7d67055`, `Enterprise=556001a6`, `Packaging / Release=531845e5`, `Docs=a25447cc` |
| Status   | `PVTSSF_lAHOD93k384BfXEKzhZqgJA`    | `Todo=f75ad846`, `In Progress=47fc9ee4`, `Done=98236657` |

Project ID (for `--project-id`): `PVT_kwHOD93k384BfXEK`.

### 6. Set the field values

Three independent edits — safe to run in parallel:

```
gh project item-edit --id <item-id> --project-id PVT_kwHOD93k384BfXEK \
  --field-id <priority-field-id> --single-select-option-id <priority-option-id>

gh project item-edit --id <item-id> --project-id PVT_kwHOD93k384BfXEK \
  --field-id <area-field-id> --single-select-option-id <area-option-id>

gh project item-edit --id <item-id> --project-id PVT_kwHOD93k384BfXEK \
  --field-id <status-field-id> --single-select-option-id <status-option-id>
```

Silent on success. Verify with the item-list check in step 7.

### 7. **Checkpoint** — verify the item is fully wired

```
gh project item-list 1 --owner cumberland-laboratories --format json | python -c "
import json, sys
d = json.load(sys.stdin)
for i in d['items']:
    print(f\"#{i['content']['number']} - {i['content']['title']}\")
    print(f\"  Status: {i.get('status', '?')}\")
    print(f\"  Priority: {i.get('priority', '?')}\")
    print(f\"  Area: {i.get('area', '?')}\")
"
```

Expect the issue with all three fields populated. If any shows `?` or `None`, the corresponding `item-edit` didn't stick — re-run just that edit.

### 8. Clean up the draft file

```
rm .tmp/issue-<slug>-body.md
```

Optional but tidy. `.tmp/` is gitignored so it never propagates, but stale drafts pile up if not swept.

## Common variations

### Sub-issues (parent → children)

For multi-surface initiatives, file the parent issue first, then use GitHub's sub-issue feature via the issue's web UI (there's no first-class `gh` command yet for sub-issue linking as of 2026-08-04 — `gh` covers Projects, but sub-issue hierarchy is a newer feature and the CLI hasn't caught up). Alternative: reference the parent from each child body with `Parent: #<number>` and add all children under the same Project item.

### Batch migrations from `.gator/inbox.md`

For triage-day sweeps: promote each inbox item to a fresh issue using steps 1–7 back-to-back. Delete the promoted line from `inbox.md` in a single follow-on commit. Keep the promotion audit trail in the commit message: `"promoted inbox items → issues #N, #N+1, #N+2"`.

### Retroactively assigning a Milestone

`gh issue edit <number> --milestone "<milestone-name>"` — after the milestone exists (`gh api repos/... POST milestones`). Not required for the current workflow; Priority + Target Release field would be added to the Project if this pattern becomes routine.

## Notes

- **Silent `item-edit` failure mode**: `gh project item-edit` prints nothing on success AND nothing on some failure classes (e.g. wrong option ID for the wrong field). Always run step 7 after a batch of edits.
- **The Gator project is "user-owned" not "org-owned"** at the GitHub API level (`type: "User"` in `gh project list` JSON) because `cumberland-laboratories` is a User-type account, not an Organization-type account. Doesn't affect functionality — commands and URLs work the same — but is worth knowing if a future setup step assumes org-scoped API endpoints.
- **Do not create field options via CLI without adding them to the field's option list first.** Single-select fields silently reject unknown options through some code paths. Add via the Project UI (Settings → Fields → edit → add option), then re-run step 5 to capture the new option ID.
- **When retiring `.gator/issues.md` items into GitHub**, reference the original entry in the issue body (`### References` section) so the git-blame trail stays walkable.

## Connections

- `.gator/vault/artifacts/2026-08-04-github-issue-tracking-outline.md` — the design rationale for moving off `issues.md`
- `.gator/inbox.md` — zero-friction capture surface (pre-issue intake)
- `.gator/procedures/release-and-deploy.md` — release cadence (issue triage before release: filter by Priority + `Status = Todo/In Progress`)
